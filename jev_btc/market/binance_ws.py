"""Binance USDⓈ-M Futures public market data over WebSocket (+ open interest via REST).

Only public endpoints are used. No API key, no orders.

Streams (one combined connection):
  <btc>@aggTrade          trades (price, qty, taker side)
  <btc>@bookTicker        best bid / ask
  <btc>@depth20@100ms     top-20 order book (full snapshot every message)
  <btc>@markPrice@1s      mark price + funding rate
  <eth>@bookTicker        reference asset best bid / ask
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field

import httpx
import websockets

from config import Config

log = logging.getLogger(__name__)

TRADE_HISTORY_SEC = 600  # keep 10 minutes of trades in memory


@dataclass
class Trade:
    recv_ts: float  # local receive time (seconds)
    price: float
    qty: float
    is_buy: bool  # True = taker bought (aggressive buyer)


@dataclass
class MarketState:
    """Latest known market state. Updated by BinanceStream, read by FeatureEngine."""

    bid: float | None = None
    ask: float | None = None
    bid_qty: float | None = None
    ask_qty: float | None = None
    book_ts: float = 0.0

    depth_bids: list[tuple[float, float]] = field(default_factory=list)
    depth_asks: list[tuple[float, float]] = field(default_factory=list)
    depth_ts: float = 0.0

    trades: deque = field(default_factory=deque)
    last_trade_price: float | None = None
    trade_ts: float = 0.0

    ref_bid: float | None = None
    ref_ask: float | None = None
    ref_ts: float = 0.0

    mark_price: float | None = None
    funding_rate: float | None = None
    mark_ts: float = 0.0

    open_interest: float | None = None
    oi_ts: float = 0.0

    connected: bool = False
    reconnects: int = 0
    messages: int = 0

    def prune_trades(self, now: float) -> None:
        cutoff = now - TRADE_HISTORY_SEC
        while self.trades and self.trades[0].recv_ts < cutoff:
            self.trades.popleft()


class BinanceStream:
    def __init__(self, cfg: Config, state: MarketState):
        self.cfg = cfg
        self.state = state
        s, r = cfg.symbol.lower(), cfg.ref_symbol.lower()
        self._stream_btc_trade = f"{s}@aggTrade"
        self._stream_btc_book = f"{s}@bookTicker"
        self._stream_btc_depth = f"{s}@depth20@100ms"
        self._stream_btc_mark = f"{s}@markPrice@1s"
        self._stream_ref_book = f"{r}@bookTicker"
        streams = [
            self._stream_btc_trade,
            self._stream_btc_book,
            self._stream_btc_depth,
            self._stream_btc_mark,
            self._stream_ref_book,
        ]
        self.url = f"{cfg.binance_ws_url}?streams={'/'.join(streams)}"

    # ---------------- WebSocket ----------------
    async def run(self) -> None:
        """Connect forever. Reconnects with exponential backoff on any error or stale feed."""
        backoff = 1.0
        while True:
            try:
                log.info("Connecting to %s", self.url)
                async with websockets.connect(
                    self.url, ping_interval=20, ping_timeout=20, close_timeout=5, max_size=2**22
                ) as ws:
                    self.state.connected = True
                    backoff = 1.0
                    log.info("WebSocket connected")
                    while True:
                        # No message for a while = silent dead connection -> reconnect
                        raw = await asyncio.wait_for(ws.recv(), timeout=self.cfg.ws_stale_timeout_sec)
                        self._handle_raw(raw)
            except asyncio.CancelledError:
                self.state.connected = False
                raise
            except asyncio.TimeoutError:
                log.warning("WebSocket stale (no data for %.0fs), reconnecting", self.cfg.ws_stale_timeout_sec)
            except Exception as e:  # network errors, server close (Binance closes every 24h), etc.
                log.warning("WebSocket error: %r", e)
            self.state.connected = False
            self.state.reconnects += 1
            sleep = backoff + random.uniform(0, 0.5)
            log.info("Reconnecting in %.1fs", sleep)
            await asyncio.sleep(sleep)
            backoff = min(backoff * 2, 30.0)

    def _handle_raw(self, raw: str | bytes) -> None:
        try:
            msg = json.loads(raw)
            stream, data = msg["stream"], msg["data"]
        except (ValueError, KeyError, TypeError):
            log.debug("Ignoring malformed message: %.200s", raw)
            return
        try:
            self.handle(stream, data, time.time())
        except (KeyError, ValueError, TypeError, IndexError) as e:
            log.warning("Bad payload on %s: %r", stream, e)

    def handle(self, stream: str, d: dict, now: float) -> None:
        st = self.state
        st.messages += 1
        if stream == self._stream_btc_trade:
            t = Trade(now, float(d["p"]), float(d["q"]), is_buy=not d["m"])  # m=True -> buyer is maker -> taker sold
            st.trades.append(t)
            st.last_trade_price = t.price
            st.trade_ts = now
            st.prune_trades(now)
        elif stream == self._stream_btc_book:
            bid, ask = float(d["b"]), float(d["a"])
            if bid <= 0 or ask <= 0 or bid > ask:
                return
            st.bid, st.ask = bid, ask
            st.bid_qty, st.ask_qty = float(d["B"]), float(d["A"])
            st.book_ts = now
        elif stream == self._stream_btc_depth:
            st.depth_bids = [(float(p), float(q)) for p, q in d["b"]]
            st.depth_asks = [(float(p), float(q)) for p, q in d["a"]]
            st.depth_ts = now
        elif stream == self._stream_btc_mark:
            st.mark_price = float(d["p"])
            st.funding_rate = float(d["r"]) if d.get("r") not in (None, "") else None
            st.mark_ts = now
        elif stream == self._stream_ref_book:
            bid, ask = float(d["b"]), float(d["a"])
            if bid <= 0 or ask <= 0 or bid > ask:
                return
            st.ref_bid, st.ref_ask = bid, ask
            st.ref_ts = now

    # ---------------- Open interest (REST) ----------------
    async def poll_open_interest(self) -> None:
        url = f"{self.cfg.binance_rest_url}/fapi/v1/openInterest"
        async with httpx.AsyncClient(timeout=5.0) as client:
            while True:
                try:
                    r = await client.get(url, params={"symbol": self.cfg.symbol})
                    if r.status_code == 200:
                        self.state.open_interest = float(r.json()["openInterest"])
                        self.state.oi_ts = time.time()
                    elif r.status_code in (418, 429):
                        wait = float(r.headers.get("Retry-After", 60))
                        log.warning("Open interest rate limited, sleeping %.0fs", wait)
                        await asyncio.sleep(wait)
                    else:
                        log.warning("Open interest HTTP %s: %.200s", r.status_code, r.text)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.warning("Open interest error: %r", e)
                await asyncio.sleep(self.cfg.open_interest_poll_sec)
