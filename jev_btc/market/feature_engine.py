"""Turns the live MarketState into one small feature dict per second.

Everything the model sees is computed here, so the raw order book never leaves Python.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from config import Config
from market.binance_ws import MarketState

HISTORY_SEC = 600
VOL_Z_LOOKBACK_SEC = 300  # z-score of the last 10s volume vs. the previous 5 minutes
VOLATILITY_WINDOW_SEC = 30


@dataclass
class _Second:
    price: float
    ref_mid: float | None
    volume: float
    buy_volume: float
    sell_volume: float
    n_trades: int
    open_interest: float | None


def _ret(now: float | None, past: float | None) -> float | None:
    if now is None or past is None or past <= 0:
        return None
    return now / past - 1.0


def _imbalance(bids: list[tuple[float, float]], asks: list[tuple[float, float]], levels: int) -> float | None:
    b = sum(q for _, q in bids[:levels])
    a = sum(q for _, q in asks[:levels])
    return (b - a) / (b + a) if (b + a) > 0 else None


class FeatureEngine:
    def __init__(self, cfg: Config, state: MarketState):
        self.cfg = cfg
        self.state = state
        self.hist: dict[int, _Second] = {}
        self._order: deque[int] = deque()
        self.first_ts: int | None = None

    def _price(self, ts_state: MarketState) -> float | None:
        if self.cfg.price_source == "last":
            return ts_state.last_trade_price
        if ts_state.bid is None or ts_state.ask is None:
            return None
        return (ts_state.bid + ts_state.ask) / 2

    def _get(self, ts: int) -> _Second | None:
        return self.hist.get(ts)

    def _window(self, ts: int, seconds: int) -> list[_Second]:
        return [s for t in range(ts - seconds + 1, ts + 1) if (s := self.hist.get(t)) is not None]

    def snapshot(self, ts: int, now: float) -> dict | None:
        """Build the snapshot for integer second `ts`.

        Returns None if core market data is missing/stale (nothing is stored then).
        The returned dict has `ready=False` during warm-up or if some features are missing;
        such rows are still saved (they are needed as future prices for labeling)
        but are not sent to Jev.
        """
        st = self.state
        max_age = self.cfg.max_data_age_sec
        if st.bid is None or now - st.book_ts > max_age:
            return None
        price = self._price(st)
        if price is None:
            return None

        # --- aggregate trades of the last second: [ts-1, ts) ---
        vol = buy = sell = 0.0
        n = 0
        for t in reversed(st.trades):
            if t.recv_ts >= ts:
                continue
            if t.recv_ts < ts - 1:
                break
            vol += t.qty
            n += 1
            if t.is_buy:
                buy += t.qty
            else:
                sell += t.qty

        ref_mid = None
        if st.ref_bid is not None and now - st.ref_ts <= max_age:
            ref_mid = (st.ref_bid + st.ref_ask) / 2
        oi = st.open_interest if (st.open_interest is not None and now - st.oi_ts <= 60) else None

        if ts in self.hist:  # duplicate second (should not happen) -> ignore
            return None
        self.hist[ts] = _Second(price, ref_mid, vol, buy, sell, n, oi)
        self._order.append(ts)
        while self._order and self._order[0] < ts - HISTORY_SEC:
            self.hist.pop(self._order.popleft(), None)
        if self.first_ts is None:
            self.first_ts = ts

        f: dict = {"ts": ts, "price": price}
        f["best_bid"], f["best_ask"] = st.bid, st.ask
        f["last_trade_price"] = st.last_trade_price
        f["spread_bps"] = (st.ask - st.bid) / price * 1e4

        # returns
        for k in (1, 3, 5, 10, 30):
            past = self._get(ts - k)
            f[f"ret_{k}s"] = _ret(price, past.price if past else None)

        # volume
        w10 = self._window(ts, 10)
        vol10 = sum(s.volume for s in w10)
        buy10 = sum(s.buy_volume for s in w10)
        sell10 = sum(s.sell_volume for s in w10)
        f["volume_1s"] = vol
        f["volume_10s"] = vol10
        f["trades_10s"] = sum(s.n_trades for s in w10)
        f["buy_volume_10s"] = buy10
        f["sell_volume_10s"] = sell10
        f["taker_buy_ratio_10s"] = buy10 / vol10 if vol10 > 0 else None  # 0..1, 0.5 = balanced
        f["buy_sell_ratio_10s"] = min(buy10 / sell10, 100.0) if sell10 > 0 else None
        w3 = self._window(ts, 3)
        b3, s3 = sum(s.buy_volume for s in w3), sum(s.sell_volume for s in w3)
        f["taker_buy_ratio_3s"] = b3 / (b3 + s3) if (b3 + s3) > 0 else None
        f["volume_zscore"] = self._volume_zscore(ts, vol10)

        # volatility: std of 1s log returns
        f["volatility_30s"] = self._volatility(ts)

        # order book
        f["obi_top1"] = (
            (st.bid_qty - st.ask_qty) / (st.bid_qty + st.ask_qty)
            if st.bid_qty is not None and (st.bid_qty + st.ask_qty) > 0
            else None
        )
        depth_ok = now - st.depth_ts <= max_age and st.depth_bids and st.depth_asks
        f["obi_top5"] = _imbalance(st.depth_bids, st.depth_asks, 5) if depth_ok else None
        f["obi_top20"] = _imbalance(st.depth_bids, st.depth_asks, 20) if depth_ok else None
        if st.bid_qty and st.ask_qty:
            micro = (st.ask * st.bid_qty + st.bid * st.ask_qty) / (st.bid_qty + st.ask_qty)
            f["microprice_dev_bps"] = (micro - price) / price * 1e4
        else:
            f["microprice_dev_bps"] = None

        # reference asset (ETH)
        for k in (3, 10):
            past = self._get(ts - k)
            f[f"eth_ret_{k}s"] = _ret(ref_mid, past.ref_mid if past else None)
        f["btc_minus_eth_ret_10s"] = (
            f["ret_10s"] - f["eth_ret_10s"] if f["ret_10s"] is not None and f["eth_ret_10s"] is not None else None
        )

        # derivatives
        f["funding_rate"] = st.funding_rate if now - st.mark_ts <= 30 else None
        f["mark_premium_bps"] = (st.mark_price - price) / price * 1e4 if st.mark_price and f["funding_rate"] is not None else None
        f["open_interest"] = oi
        past60 = self._get(ts - 60)
        f["oi_change_60s"] = _ret(oi, past60.open_interest if past60 else None)

        core = ("ret_1s", "ret_3s", "ret_10s", "obi_top5", "spread_bps", "eth_ret_10s")
        warm = self.first_ts is not None and ts - self.first_ts >= self.cfg.warmup_sec
        f["ready"] = bool(warm and all(f.get(k) is not None for k in core))
        return f

    def _volume_zscore(self, ts: int, vol10: float) -> float | None:
        vols = np.array(
            [s.volume if (s := self.hist.get(t)) else np.nan for t in range(ts - VOL_Z_LOOKBACK_SEC, ts - 9)]
        )
        if np.count_nonzero(~np.isnan(vols)) < 60:
            return None
        vols = np.nan_to_num(vols, nan=np.nanmean(vols))
        sums = np.convolve(vols, np.ones(10), mode="valid")  # rolling 10s volume
        sd = sums.std()
        return float((vol10 - sums.mean()) / sd) if sd > 0 else None

    def _volatility(self, ts: int) -> float | None:
        prices = [s.price for t in range(ts - VOLATILITY_WINDOW_SEC, ts + 1) if (s := self.hist.get(t))]
        if len(prices) < 10:
            return None
        r = np.diff(np.log(prices))
        return float(r.std())


def clean_number(x, digits: int = 6):
    """Round for compact JSON; NaN/inf -> None."""
    if x is None or isinstance(x, bool):
        return x
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
        return float(f"{x:.{digits}g}")
    return x
