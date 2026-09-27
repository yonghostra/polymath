"""Offline tests (no Binance, no Jev). Run:  python -m pytest tests -q"""
from __future__ import annotations

import asyncio
import json
import random
import sys
from pathlib import Path

import httpx
import pytest
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config  # noqa: E402
from evaluation.evaluator import evaluate, evaluate_baselines, format_report  # noqa: E402
from jev.client import (JevClient, JevHTTPError, JevMalformedResponse, JevRateLimited,  # noqa: E402
                        MockJevClient, parse_choice)
from jev.predictor import Prediction, Predictor, baselines, build_questions, build_state  # noqa: E402
from market.binance_ws import BinanceStream, MarketState  # noqa: E402
from market.feature_engine import FeatureEngine  # noqa: E402
from storage.database import Database, classify  # noqa: E402


def make_cfg(tmp_path, **kw) -> Config:
    cfg = Config()
    cfg.db_path = str(tmp_path / "t.db")
    cfg.jev_api_key = "test"
    cfg.warmup_sec = 5
    cfg.jev_max_retries = 1
    for k, v in kw.items():
        setattr(cfg, k, v)
    return cfg


def feed_second(stream: BinanceStream, t0: float, btc: float, eth: float, rng: random.Random) -> None:
    """Push ~10 synthetic Binance messages spread across one second."""
    for i in range(10):
        now = t0 + i * 0.1
        stream.handle(stream._stream_btc_book, {"b": f"{btc - 0.05}", "a": f"{btc + 0.05}",
                                                "B": f"{rng.uniform(1, 5)}", "A": f"{rng.uniform(1, 5)}"}, now)
        stream.handle(stream._stream_btc_trade, {"p": f"{btc}", "q": f"{rng.uniform(0.01, 1)}",
                                                 "m": rng.random() < 0.5}, now)
        stream.handle(stream._stream_ref_book, {"b": f"{eth - 0.01}", "a": f"{eth + 0.01}"}, now)
    stream.handle(stream._stream_btc_depth, {"b": [[f"{btc - 0.1 * k}", "2"] for k in range(1, 21)],
                                             "a": [[f"{btc + 0.1 * k}", "1"] for k in range(1, 21)]}, t0 + 0.5)
    stream.handle(stream._stream_btc_mark, {"p": f"{btc}", "r": "0.0001"}, t0 + 0.5)


def test_full_pipeline_with_mock_jev(tmp_path):
    cfg = make_cfg(tmp_path)
    state = MarketState()
    stream = BinanceStream(cfg, state)
    engine = FeatureEngine(cfg, state)
    db = Database(cfg.db_path)
    run = db.start_run("test", cfg.public_dict())
    rng = random.Random(1)
    btc, eth = 67000.0, 3500.0
    T0 = 1_700_000_000
    client = MockJevClient(cfg, on_call=lambda r: db.insert_api_call(run, r))
    client.delay = (0, 0)
    predictor = Predictor(cfg, client)
    ready = 0
    for k in range(400):
        btc *= 1 + rng.gauss(0, 0.0002)
        eth *= 1 + rng.gauss(0, 0.0002)
        feed_second(stream, T0 + k - 1, btc, eth, rng)
        f = engine.snapshot(T0 + k, T0 + k + 0.02)
        assert f is not None
        assert db.insert_snapshot(run, f, baselines(f))
        assert not db.insert_snapshot(run, f, baselines(f))  # duplicate second ignored
        if f["ready"]:
            ready += 1
            p = asyncio.run(predictor.predict(f))
            db.insert_prediction(run, p, 1)
        db.label_pending(cfg.horizon_sec, cfg.flat_threshold, T0 + k)

    assert ready > 350
    last = f
    for key in ("ret_10s", "obi_top5", "volume_zscore", "volatility_30s", "eth_ret_10s", "taker_buy_ratio_10s"):
        assert last[key] is not None, key
    assert last["obi_top5"] == pytest.approx((10 - 5) / 15)  # bids 2 vs asks 1 per level

    # the Jev input is small JSON, never the raw book
    state_str = build_state(last, cfg)
    assert len(state_str) < 1500 and "depth" not in state_str

    pred = db.labeled_predictions()
    assert len(pred) > 300
    # check a label by hand
    row = pred.iloc[0]
    fut = db.conn.execute("SELECT price FROM snapshots WHERE ts=?", (int(row.ts) + 10,)).fetchone()[0]
    assert row.future_return == pytest.approx(fut / row.price - 1)
    assert row.outcome == classify(row.future_return, cfg.flat_threshold)

    ev = evaluate(pred, cfg.high_conf_prob)
    assert 0.35 < ev["jev"]["accuracy"] < 0.65  # random predictor ~ 50%
    base = evaluate_baselines(db.labeled_snapshots(), pred["ts"])
    report = format_report(ev, base, db.api_stats(run), cfg)
    assert "Jev high-conf" in report and "base:momentum" in report
    assert db.api_stats(run)["total_calls"] == len(db.conn.execute("SELECT * FROM predictions").fetchall())

    # relabel with a different threshold
    n = db.relabel_all(cfg.horizon_sec, 0.01)
    assert n > 0
    assert set(db.labeled_snapshots()["outcome"]) == {"FLAT"}
    db.close()


def test_missing_data_returns_none(tmp_path):
    cfg = make_cfg(tmp_path)
    state = MarketState()
    engine = FeatureEngine(cfg, state)
    assert engine.snapshot(100, 100.0) is None  # nothing received yet
    stream = BinanceStream(cfg, state)
    feed_second(stream, 99, 67000, 3500, random.Random(0))
    assert engine.snapshot(100, 100.0) is not None
    assert engine.snapshot(200, 200.0) is None  # book is 100s old -> stale


def test_label_gap_marks_na(tmp_path):
    db = Database(str(tmp_path / "g.db"))
    run = db.start_run("t", {})
    for ts in (0, 1, 2):
        db.insert_snapshot(run, {"ts": ts, "price": 100.0, "ready": True}, {})
    db.insert_snapshot(run, {"ts": 11, "price": 100.1, "ready": True}, {})
    db.label_pending(10, 0.0002, now_ts=12)
    rows = dict(db.conn.execute("SELECT ts, outcome FROM snapshots").fetchall())
    assert rows[1] == "UP" and rows[0] is None and rows[2] is None  # 0 and 2 still waiting
    db.label_pending(10, 0.0002, now_ts=200)
    rows = dict(db.conn.execute("SELECT ts, outcome FROM snapshots").fetchall())
    assert rows[0] == "NA" and rows[2] == "NA"


# ---------------- Jev adapter ----------------
def test_parse_choice():
    a = parse_choice({"choice": "up", "confidence": 0.8, "probabilities": {"up": 0.78, "down": 0.22}}, ["up", "down"])
    assert a.probabilities["up"] == pytest.approx(0.78) and a.confidence == 0.8
    for bad in (None, {}, {"probabilities": {"up": 0.7}}, {"probabilities": {"up": 1.5, "down": 0.1}},
                {"probabilities": {"up": 0.5, "down": 0.1}}, {"probabilities": {"up": "x", "down": 0.5}}):
        with pytest.raises(JevMalformedResponse):
            parse_choice(bad, ["up", "down"])


def _client_with(handler, tmp_path, calls):
    cfg = make_cfg(tmp_path, jev_max_calls_per_sec=1000)
    c = JevClient(cfg, on_call=calls.append)
    c.http = httpx.AsyncClient(base_url="https://x", headers=c.http.headers, transport=httpx.MockTransport(handler))
    return c, build_questions(cfg)


GOOD = {"model": "jev-1.13.0", "usage": {"input_tokens": 400, "output_tokens": 50},
        "answers": {"direction": {"type": "choice", "choice": "up", "confidence": 0.8,
                                  "probabilities": {"up": 0.78, "down": 0.22}}}}


def test_client_success_and_request_shape(tmp_path):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers["authorization"]
        seen["path"] = req.url.path
        return httpx.Response(200, json=GOOD)

    calls = []
    c, q = _client_with(handler, tmp_path, calls)
    res = asyncio.run(c.decide("{}", q))
    assert res.answers["direction"].probabilities["up"] == pytest.approx(0.78)
    assert seen["path"] == "/v1/systemone" and seen["auth"] == "Bearer test"
    assert seen["body"]["questions"]["direction"]["type"] == "choice"
    assert calls[0].ok and calls[0].cost_usd == pytest.approx(400 / 1e6 * 0.042)


def test_client_retries_then_fails(tmp_path):
    n = {"k": 0}

    def handler(req):
        n["k"] += 1
        return httpx.Response(429, headers={"Retry-After": "0"})

    calls = []
    c, q = _client_with(handler, tmp_path, calls)
    with pytest.raises(JevRateLimited):
        asyncio.run(c.decide("{}", q))
    assert n["k"] == 2 and all(not r.ok for r in calls)  # 1 try + 1 retry


def test_client_5xx_then_ok_and_4xx_no_retry(tmp_path):
    seq = [httpx.Response(503), httpx.Response(200, json=GOOD)]
    c, q = _client_with(lambda req: seq.pop(0), tmp_path, [])
    assert asyncio.run(c.decide("{}", q)).attempts == 2

    n = {"k": 0}

    def h400(req):
        n["k"] += 1
        return httpx.Response(400, json={"error": "bad"})

    c, q = _client_with(h400, tmp_path, [])
    with pytest.raises(JevHTTPError):
        asyncio.run(c.decide("{}", q))
    assert n["k"] == 1


def test_client_malformed(tmp_path):
    c, q = _client_with(lambda req: httpx.Response(200, json={"answers": {"direction": {"x": 1}}}), tmp_path, [])
    with pytest.raises(JevMalformedResponse):
        asyncio.run(c.decide("{}", q))
    c, q = _client_with(lambda req: httpx.Response(200, text="<html>"), tmp_path, [])
    with pytest.raises(JevMalformedResponse):
        asyncio.run(c.decide("{}", q))


# ---------------- WebSocket reconnect ----------------
def test_websocket_reconnects(tmp_path):
    async def scenario():
        connections = {"n": 0}

        async def server(ws):
            connections["n"] += 1
            for i in range(3):
                await ws.send(json.dumps({"stream": "btcusdt@bookTicker",
                                          "data": {"b": "100", "a": "101", "B": "1", "A": "1"}}))
                await ws.send("not json")  # malformed message must be ignored
            await ws.close()  # server drops us -> client must reconnect

        async with websockets.serve(server, "127.0.0.1", 0) as srv:
            port = srv.sockets[0].getsockname()[1]
            cfg = make_cfg(tmp_path, binance_ws_url=f"ws://127.0.0.1:{port}/stream")
            state = MarketState()
            task = asyncio.create_task(BinanceStream(cfg, state).run())
            for _ in range(100):
                await asyncio.sleep(0.1)
                if connections["n"] >= 2:
                    break
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            return connections["n"], state

    n, state = asyncio.run(scenario())
    assert n >= 2 and state.reconnects >= 1 and state.bid == 100.0
