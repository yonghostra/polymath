"""SQLite storage. One file, no server. Safe to read with pandas while the collector runs (WAL mode).

Tables
  runs         one row per program start (config saved as JSON)
  snapshots    one row per second: price, all features (JSON), baselines, and the 10s-later label
  predictions  one row per Jev prediction (joined to snapshots by ts)
  api_calls    one row per Jev HTTP attempt (cost / reliability)
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    started_at  REAL NOT NULL,
    mode        TEXT NOT NULL,
    config_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    ts             INTEGER PRIMARY KEY,   -- unix second (duplicates are ignored)
    run_id         TEXT,
    price          REAL NOT NULL,
    ready          INTEGER NOT NULL,      -- 1 = full features, eligible for prediction
    features_json  TEXT NOT NULL,
    base_momentum  REAL,
    base_reversal  REAL,
    base_obi       REAL,
    base_flow      REAL,
    future_price   REAL,                  -- price at ts + horizon
    future_return  REAL,
    outcome        TEXT,                  -- UP / DOWN / FLAT / NA (no future price)
    horizon_sec    INTEGER,
    threshold      REAL
);
CREATE INDEX IF NOT EXISTS idx_snap_unlabeled ON snapshots(outcome) WHERE outcome IS NULL;
CREATE TABLE IF NOT EXISTS predictions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    ts              INTEGER NOT NULL,
    price           REAL NOT NULL,
    up_probability  REAL NOT NULL,
    down_probability REAL NOT NULL,
    confidence      REAL,
    model           TEXT,
    latency_ms      REAL,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    predict_every_sec INTEGER,
    created_at      REAL NOT NULL,
    UNIQUE(run_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_pred_ts ON predictions(ts);
CREATE TABLE IF NOT EXISTS api_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    created_at    REAL NOT NULL,
    ok            INTEGER NOT NULL,
    error_type    TEXT,
    http_status   INTEGER,
    latency_ms    REAL,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    cost_usd      REAL
);
"""


def classify(future_return: float, threshold: float) -> str:
    if future_return >= threshold:
        return "UP"
    if future_return <= -threshold:
        return "DOWN"
    return "FLAT"


class Database:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.commit()
        finally:
            self.conn.close()

    # ---------- writes ----------
    def start_run(self, mode: str, config: dict) -> str:
        run_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.conn.execute(
            "INSERT INTO runs VALUES (?,?,?,?)", (run_id, time.time(), mode, json.dumps(config, default=str))
        )
        self.conn.commit()
        return run_id

    def insert_snapshot(self, run_id: str, f: dict, base: dict) -> bool:
        """Returns False if this second already exists (duplicate timestamp)."""
        cur = self.conn.execute(
            """INSERT OR IGNORE INTO snapshots
               (ts, run_id, price, ready, features_json, base_momentum, base_reversal, base_obi, base_flow)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                f["ts"], run_id, f["price"], int(f["ready"]), json.dumps(f, separators=(",", ":")),
                base.get("base_momentum"), base.get("base_reversal"), base.get("base_obi"), base.get("base_flow"),
            ),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def insert_prediction(self, run_id: str, p, predict_every_sec: int) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO predictions
               (run_id, ts, price, up_probability, down_probability, confidence, model, latency_ms,
                input_tokens, output_tokens, predict_every_sec, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, p.ts, p.price, p.up_probability, p.down_probability, p.confidence, p.model,
                p.latency_ms, p.input_tokens, p.output_tokens, predict_every_sec, time.time(),
            ),
        )
        self.conn.commit()

    def insert_api_call(self, run_id: str, rec) -> None:
        self.conn.execute(
            """INSERT INTO api_calls
               (run_id, created_at, ok, error_type, http_status, latency_ms, input_tokens, output_tokens, cost_usd)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (run_id, time.time(), int(rec.ok), rec.error_type, rec.http_status, rec.latency_ms,
             rec.input_tokens, rec.output_tokens, rec.cost_usd),
        )
        self.conn.commit()

    # ---------- labeling ----------
    def label_pending(self, horizon: int, threshold: float, now_ts: int, give_up_after: int = 60) -> int:
        """Attach the real outcome to every snapshot whose ts + horizon has passed.

        future price = price of the snapshot at exactly ts + horizon.
        If that second is missing (disconnect), the row is marked NA after `give_up_after` seconds
        instead of using a wrong horizon.
        """
        rows = self.conn.execute(
            """SELECT s.ts, s.price, f.price
               FROM snapshots s LEFT JOIN snapshots f ON f.ts = s.ts + ?
               WHERE s.outcome IS NULL AND s.ts <= ?""",
            (horizon, now_ts - horizon),
        ).fetchall()
        updates = []
        for ts, price, fut in rows:
            if fut is not None:
                r = fut / price - 1.0
                updates.append((fut, r, classify(r, threshold), horizon, threshold, ts))
            elif ts <= now_ts - horizon - give_up_after:
                updates.append((None, None, "NA", horizon, threshold, ts))
        self.conn.executemany(
            """UPDATE snapshots SET future_price=?, future_return=?, outcome=?, horizon_sec=?, threshold=?
               WHERE ts=?""",
            updates,
        )
        self.conn.commit()
        return len(updates)

    def relabel_all(self, horizon: int, threshold: float) -> int:
        """Recompute every label (e.g. after changing FLAT_THRESHOLD or HORIZON_SEC)."""
        self.conn.execute(
            "UPDATE snapshots SET future_price=NULL, future_return=NULL, outcome=NULL, horizon_sec=NULL, threshold=NULL"
        )
        self.conn.commit()
        return self.label_pending(horizon, threshold, now_ts=int(time.time()), give_up_after=0)

    # ---------- reads ----------
    def labeled_predictions(self, run_id: str | None = None) -> pd.DataFrame:
        q = """SELECT p.*, s.future_price, s.future_return, s.outcome
               FROM predictions p JOIN snapshots s ON s.ts = p.ts
               WHERE s.outcome IN ('UP','DOWN','FLAT')"""
        params: tuple = ()
        if run_id:
            q += " AND p.run_id = ?"
            params = (run_id,)
        return pd.read_sql_query(q + " ORDER BY p.ts", self.conn, params=params)

    def labeled_snapshots(self) -> pd.DataFrame:
        return pd.read_sql_query(
            """SELECT ts, price, ready, base_momentum, base_reversal, base_obi, base_flow,
                      future_return, outcome
               FROM snapshots WHERE outcome IN ('UP','DOWN','FLAT') ORDER BY ts""",
            self.conn,
        )

    def api_stats(self, run_id: str | None = None) -> dict:
        where, params = ("WHERE run_id = ?", (run_id,)) if run_id else ("", ())
        row = self.conn.execute(
            f"""SELECT COUNT(*), COALESCE(SUM(ok),0), COALESCE(SUM(cost_usd),0),
                       COALESCE(SUM(input_tokens),0), AVG(CASE WHEN ok=1 THEN latency_ms END)
                FROM api_calls {where}""",
            params,
        ).fetchone()
        n_pred = self.conn.execute(f"SELECT COUNT(*) FROM predictions {where}", params).fetchone()[0]
        errors = dict(
            self.conn.execute(
                f"SELECT error_type, COUNT(*) FROM api_calls {where} {'AND' if where else 'WHERE'} ok=0 GROUP BY error_type",
                params,
            ).fetchall()
        )
        total, ok, cost, tokens, lat = row
        return {
            "total_calls": total,
            "successful_calls": ok,
            "failed_calls": total - ok,
            "errors": errors,
            "predictions": n_pred,
            "estimated_cost_usd": cost,
            "input_tokens": tokens,
            "avg_latency_ms": lat,
            "cost_per_1000_predictions": (cost / n_pred * 1000) if n_pred else None,
        }

    def export_csv(self, out_dir: str) -> list[str]:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        paths = []
        for table in ("snapshots", "predictions", "api_calls", "runs"):
            df = pd.read_sql_query(f"SELECT * FROM {table}", self.conn)
            p = str(Path(out_dir) / f"{table}.csv")
            df.to_csv(p, index=False)
            paths.append(p)
        return paths
