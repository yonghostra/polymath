"""Jev BTC 10-second direction experiment.  PAPER ONLY - no orders are ever sent.

  python main.py collect    Phase 1: market data + features -> SQLite (no Jev calls)
  python main.py predict    Phase 2+3: collect + Jev prediction every PREDICT_EVERY_SEC + live labeling
  python main.py label      Phase 3: (re)label stored snapshots, e.g. after changing FLAT_THRESHOLD
  python main.py report     Phase 3: accuracy / baseline / cost report
  python main.py export     dump all tables to data/csv/*.csv
  python main.py jev-test   send ONE request to Jev and print the raw response (check the API shape)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config, load_config  # noqa: E402
from evaluation.evaluator import evaluate, evaluate_baselines, format_report  # noqa: E402
from jev.client import JevError, make_client  # noqa: E402
from jev.predictor import Predictor, baselines, build_questions, build_state  # noqa: E402
from market.binance_ws import BinanceStream, MarketState  # noqa: E402
from market.feature_engine import FeatureEngine  # noqa: E402
from storage.database import Database  # noqa: E402

log = logging.getLogger("main")


def setup_logging(cfg: Config) -> None:
    handler = RotatingFileHandler(cfg.log_path, maxBytes=20_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


class Experiment:
    def __init__(self, cfg: Config, use_jev: bool):
        self.cfg = cfg
        self.use_jev = use_jev
        self.db = Database(cfg.db_path)
        self.state = MarketState()
        self.stream = BinanceStream(cfg, self.state)
        self.engine = FeatureEngine(cfg, self.state)
        self.run_id = self.db.start_run("predict" if use_jev else "collect", cfg.public_dict())
        self.client = make_client(cfg, on_call=lambda rec: self.db.insert_api_call(self.run_id, rec)) if use_jev else None
        self.predictor = Predictor(cfg, self.client) if use_jev else None
        self.inflight: set[asyncio.Task] = set()
        self.stop = asyncio.Event()
        self.last_features: dict | None = None
        self.last_pred = None
        self.counters = {"snapshots": 0, "skipped_no_data": 0, "duplicates": 0, "pred_ok": 0,
                         "pred_failed": 0, "pred_skipped_busy": 0}
        self.stats: dict = {}
        self.api: dict = {}
        self.started = time.time()

    # ---------- main loops ----------
    async def snapshot_loop(self) -> None:
        while not self.stop.is_set():
            now = time.time()
            await asyncio.sleep(max(0.0, 1.0 - (now % 1.0)) + 0.02)  # just after each full second
            now = time.time()
            ts = int(now)
            try:
                f = self.engine.snapshot(ts, now)
                if f is None:
                    self.counters["skipped_no_data"] += 1
                else:
                    self.last_features = f
                    if self.db.insert_snapshot(self.run_id, f, baselines(f)):
                        self.counters["snapshots"] += 1
                        if self.use_jev and f["ready"] and ts % self.cfg.predict_every_sec == 0:
                            self._spawn_prediction(f)
                    else:
                        self.counters["duplicates"] += 1
                self.db.label_pending(self.cfg.horizon_sec, self.cfg.flat_threshold, ts)
            except Exception:
                log.exception("snapshot loop error (continuing)")

    def _spawn_prediction(self, f: dict) -> None:
        if len(self.inflight) >= self.cfg.jev_max_inflight:
            self.counters["pred_skipped_busy"] += 1
            return
        task = asyncio.create_task(self._predict(f))
        self.inflight.add(task)
        task.add_done_callback(self.inflight.discard)

    async def _predict(self, f: dict) -> None:
        try:
            p = await self.predictor.predict(f)
        except JevError as e:
            self.counters["pred_failed"] += 1
            log.warning("Jev prediction skipped for ts=%s: %s: %s", f["ts"], type(e).__name__, e)
            return
        except Exception:
            self.counters["pred_failed"] += 1
            log.exception("unexpected prediction error for ts=%s", f["ts"])
            return
        self.db.insert_prediction(self.run_id, p, self.cfg.predict_every_sec)
        self.last_pred = p
        self.counters["pred_ok"] += 1

    async def stats_loop(self) -> None:
        while not self.stop.is_set():
            try:
                if self.use_jev:
                    self.stats = evaluate(self.db.labeled_predictions(self.run_id), self.cfg.high_conf_prob)
                    self.api = self.db.api_stats(self.run_id)
            except Exception:
                log.exception("stats error")
            await asyncio.sleep(10)

    async def display_loop(self) -> None:
        while not self.stop.is_set():
            await asyncio.sleep(1)
            sys.stdout.write("\033[2J\033[H" + self.render() + "\n")
            sys.stdout.flush()

    def render(self) -> str:
        f, st, c = self.last_features or {}, self.state, self.counters

        def pct(x, d=3):
            return "-" if x is None else f"{x * 100:+.{d}f}%"

        def num(x, fmt="+.2f"):
            return "-" if x is None else format(x, fmt)

        def pct1(x):
            return "-" if x is None else f"{x * 100:.1f}%"

        up = int(time.time() - self.started)
        lines = [
            f"Jev BTC experiment [{'PREDICT' if self.use_jev else 'COLLECT'}{' / MOCK' if self.cfg.jev_mock and self.use_jev else ''}]"
            f"  run={self.run_id}  uptime={up // 3600}h{up % 3600 // 60:02d}m  (PAPER ONLY, Ctrl+C to stop)",
            f"WS: {'connected' if st.connected else 'DISCONNECTED'}  reconnects={st.reconnects}  msgs={st.messages:,}",
            "",
            f"BTC: {num(f.get('price'), ',.1f')}   spread {num(f.get('spread_bps'), '.2f')} bps",
            f"1s return: {pct(f.get('ret_1s'))}   10s return: {pct(f.get('ret_10s'))}",
            f"Orderbook imbalance(top5): {num(f.get('obi_top5'))}   Buy/Sell ratio(10s): {num(f.get('buy_sell_ratio_10s'), '.2f')}",
            f"Volume z: {num(f.get('volume_zscore'))}   ETH 10s: {pct(f.get('eth_ret_10s'))}   "
            f"funding: {pct(f.get('funding_rate'), 4)}   ready: {f.get('ready', False)}",
            "",
            f"Snapshots: {c['snapshots']:,}  (no-data skips {c['skipped_no_data']}, duplicates {c['duplicates']})",
        ]
        if self.use_jev:
            p = self.last_pred
            s = self.stats
            j = s.get("jev", {})
            hc = s.get("high_conf", {})
            a = self.api
            lines += [
                "",
                f"Jev P(UP): {'-' if p is None else format(p.up_probability, '.0%')}   "
                f"Confidence: {'-' if p is None or p.confidence is None else format(p.confidence, '.0%')}   "
                f"latency: {'-' if p is None else format(p.latency_ms, '.0f') + 'ms'}",
                "",
                f"Predictions: {c['pred_ok']:,}  (failed {c['pred_failed']}, skipped-busy {c['pred_skipped_busy']}, "
                f"labeled {s.get('n', 0):,})",
                f"Accuracy: {pct1(j.get('accuracy'))}   (p-value {num(j.get('p_value'), '.3f')}, "
                f"base rate UP {pct1(s.get('base_rate_up'))})",
                f"High-confidence accuracy: {pct1(hc.get('accuracy'))}  (n={hc.get('n_non_flat', 0)})",
                "Paper PnL: - (Phase 5)",
                "",
                f"API calls: {a.get('total_calls', 0):,} ok {a.get('successful_calls', 0):,} "
                f"failed {a.get('failed_calls', 0):,}   cost ${a.get('estimated_cost_usd', 0):.4f}"
                f"   per 1k preds ${num(a.get('cost_per_1000_predictions'), '.4f')}",
            ]
        lines.append(f"\nlog: {self.cfg.log_path}")
        return "\n".join(lines)

    # ---------- lifecycle ----------
    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop.set)
            except (NotImplementedError, RuntimeError):  # Windows: Ctrl+C raises KeyboardInterrupt instead
                pass
        log.info("run %s started, mode=%s", self.run_id, "predict" if self.use_jev else "collect")
        tasks = [
            asyncio.create_task(self.stream.run(), name="ws"),
            asyncio.create_task(self.stream.poll_open_interest(), name="oi"),
            asyncio.create_task(self.snapshot_loop(), name="snap"),
            asyncio.create_task(self.stats_loop(), name="stats"),
            asyncio.create_task(self.display_loop(), name="display"),
        ]
        try:
            await self.stop.wait()
        finally:
            await self.shutdown(tasks)

    async def shutdown(self, tasks) -> None:
        print("\nShutting down...")
        self.stop.set()
        if self.inflight:  # let running Jev calls finish (max a few seconds)
            await asyncio.wait(self.inflight, timeout=self.cfg.jev_timeout_sec + 1)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.client:
            await self.client.aclose()
        self.db.label_pending(self.cfg.horizon_sec, self.cfg.flat_threshold, int(time.time()))
        self.db.close()
        log.info("run %s stopped. counters=%s", self.run_id, self.counters)
        print(f"Stopped. run={self.run_id} counters={self.counters}")
        print("Run `python main.py report` for the full statistics.")


# ---------------- other commands ----------------
def cmd_label(cfg: Config) -> None:
    db = Database(cfg.db_path)
    n = db.relabel_all(cfg.horizon_sec, cfg.flat_threshold)
    db.close()
    print(f"Relabeled {n:,} snapshots with horizon={cfg.horizon_sec}s, threshold={cfg.flat_threshold * 100:.3f}%")


def cmd_report(cfg: Config, run_id: str | None) -> None:
    db = Database(cfg.db_path)
    pred = db.labeled_predictions(run_id)
    snaps = db.labeled_snapshots()
    ev = evaluate(pred, cfg.high_conf_prob)
    base = evaluate_baselines(snaps, pred["ts"] if not pred.empty else None)
    print(format_report(ev, base, db.api_stats(run_id), cfg))
    if pred.empty and not snaps.empty:
        print(f"\n(no Jev predictions yet - baselines above use all {len(snaps):,} labeled snapshots)")
    db.close()


def cmd_export(cfg: Config) -> None:
    db = Database(cfg.db_path)
    out = Path(cfg.db_path).parent / "csv"
    for p in db.export_csv(str(out)):
        print("wrote", p)
    db.close()


async def cmd_jev_test(cfg: Config) -> None:
    sample = {
        "ts": int(time.time()), "price": 67421.5, "ret_1s": 0.0003, "ret_3s": 0.0008, "ret_5s": 0.001,
        "ret_10s": 0.0012, "ret_30s": 0.0015, "spread_bps": 0.015, "obi_top1": 0.4, "obi_top5": 0.31,
        "obi_top20": 0.12, "microprice_dev_bps": 0.004, "volume_10s": 42.1, "volume_zscore": 2.3,
        "trades_10s": 950, "taker_buy_ratio_3s": 0.66, "taker_buy_ratio_10s": 0.6, "buy_sell_ratio_10s": 1.47,
        "volatility_30s": 0.00019, "eth_ret_3s": 0.0006, "eth_ret_10s": 0.0014, "btc_minus_eth_ret_10s": -0.0002,
        "funding_rate": 0.0001, "mark_premium_bps": -0.3, "oi_change_60s": 0.0004,
    }
    state, questions = build_state(sample, cfg), build_questions(cfg)
    print("STATE:", state, "\nQUESTIONS:", json.dumps(questions, indent=2))
    client = make_client(cfg)
    try:
        if cfg.jev_mock:
            print("JEV_MOCK=1 -> mock result:", await client.decide(state, questions))
            return
        status, body, ms, _ = await client.raw_request(state, questions)
        print(f"\nHTTP {status} in {ms:.0f} ms\nRAW RESPONSE:\n{json.dumps(body, indent=2) if isinstance(body, dict) else body}")
        p = await Predictor(cfg, client).predict(sample)
        print(f"\nPARSED: P(up)={p.up_probability:.3f} P(down)={p.down_probability:.3f} "
              f"confidence={p.confidence} tokens={p.input_tokens}")
    except Exception as e:
        print(f"\nFAILED: {type(e).__name__}: {e}")
        print("Check JEV_API_KEY / JEV_BASE_URL in .env, and compare the RAW RESPONSE with jev/client.py.")
    finally:
        await client.aclose()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["collect", "predict", "label", "report", "export", "jev-test"])
    ap.add_argument("--run", help="report: only this run_id")
    args = ap.parse_args()
    cfg = load_config()
    setup_logging(cfg)

    if args.command in ("collect", "predict"):
        exp = Experiment(cfg, use_jev=args.command == "predict")
        try:
            asyncio.run(exp.run())
        except KeyboardInterrupt:  # Windows fallback; shutdown() already ran in run()'s finally
            pass
    elif args.command == "label":
        cmd_label(cfg)
    elif args.command == "report":
        cmd_report(cfg, args.run)
    elif args.command == "export":
        cmd_export(cfg)
    elif args.command == "jev-test":
        asyncio.run(cmd_jev_test(cfg))


if __name__ == "__main__":
    main()
