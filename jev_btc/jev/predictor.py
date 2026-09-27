"""Turns a feature snapshot into a Jev question and a structured prediction.

Also holds the zero-cost baselines that are stored next to every snapshot,
so Jev can be compared against simple rules on exactly the same seconds.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from config import Config
from market.feature_engine import clean_number

# Only these features are sent to Jev (small JSON, no raw order book).
JEV_FEATURES = [
    "ret_1s", "ret_3s", "ret_5s", "ret_10s", "ret_30s",
    "spread_bps", "obi_top1", "obi_top5", "obi_top20", "microprice_dev_bps",
    "volume_10s", "volume_zscore", "trades_10s",
    "taker_buy_ratio_3s", "taker_buy_ratio_10s", "buy_sell_ratio_10s",
    "volatility_30s",
    "eth_ret_3s", "eth_ret_10s", "btc_minus_eth_ret_10s",
    "funding_rate", "mark_premium_bps", "oi_change_60s",
]

QUESTION_NAME = "direction"


def build_state(features: dict, cfg: Config) -> str:
    payload = {
        "instrument": f"{cfg.symbol} perpetual futures (Binance)",
        "note": "ret_* are fractional price changes over the last N seconds; obi_* in [-1,1], positive = more bid size.",
        "features": {k: clean_number(features.get(k)) for k in JEV_FEATURES},
    }
    return json.dumps(payload, separators=(",", ":"))


def build_questions(cfg: Config) -> dict:
    h = cfg.horizon_sec
    return {
        QUESTION_NAME: {
            "type": "choice",
            "instructions": (
                f"Based on this short-term market microstructure snapshot, will the {cfg.symbol} "
                f"mid price be higher or lower {h} seconds from now than it is now?"
            ),
            "criteria": {
                "up": f"price will be higher in {h} seconds",
                "down": f"price will be lower in {h} seconds",
            },
        }
    }


@dataclass
class Prediction:
    ts: int
    price: float
    up_probability: float
    down_probability: float
    confidence: float | None
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int


class Predictor:
    def __init__(self, cfg: Config, client):
        self.cfg = cfg
        self.client = client
        self.questions = build_questions(cfg)

    async def predict(self, features: dict) -> Prediction:
        """Raises jev.client.JevError subclasses on failure (caller skips that second)."""
        res = await self.client.decide(build_state(features, self.cfg), self.questions)
        ans = res.answers[QUESTION_NAME]
        return Prediction(
            ts=features["ts"],
            price=features["price"],
            up_probability=ans.probabilities["up"],
            down_probability=ans.probabilities["down"],
            confidence=ans.confidence,
            model=res.model,
            latency_ms=res.latency_ms,
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
        )


def baselines(f: dict) -> dict:
    """Free baseline 'P(up)' values (1 / 0 / 0.5). If Jev can't beat these, it has no extra alpha."""

    def sign_prob(x):
        if x is None:
            return None
        return 1.0 if x > 0 else 0.0 if x < 0 else 0.5

    return {
        "base_momentum": sign_prob(f.get("ret_10s")),       # recent 10s trend continues
        "base_reversal": (None if f.get("ret_10s") is None else 1.0 - sign_prob(f.get("ret_10s"))),
        "base_obi": sign_prob(f.get("obi_top5")),           # more bid size -> up
        "base_flow": (None if f.get("taker_buy_ratio_10s") is None
                      else sign_prob(f["taker_buy_ratio_10s"] - 0.5)),  # more taker buying -> up
    }
