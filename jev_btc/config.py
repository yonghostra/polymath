"""All tunable settings. Values come from .env (or environment variables) with safe defaults."""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def _float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    # --- Binance (public market data only, no API key needed) ---
    symbol: str = field(default_factory=lambda: _env("SYMBOL", "BTCUSDT").upper())
    ref_symbol: str = field(default_factory=lambda: _env("REF_SYMBOL", "ETHUSDT").upper())
    binance_ws_url: str = field(default_factory=lambda: _env("BINANCE_WS_URL", "wss://fstream.binance.com/stream"))
    binance_rest_url: str = field(default_factory=lambda: _env("BINANCE_REST_URL", "https://fapi.binance.com"))
    open_interest_poll_sec: float = field(default_factory=lambda: _float("OPEN_INTEREST_POLL_SEC", 10.0))
    ws_stale_timeout_sec: float = field(default_factory=lambda: _float("WS_STALE_TIMEOUT_SEC", 10.0))
    max_data_age_sec: float = field(default_factory=lambda: _float("MAX_DATA_AGE_SEC", 5.0))

    # --- Experiment ---
    horizon_sec: int = field(default_factory=lambda: _int("HORIZON_SEC", 10))
    predict_every_sec: int = field(default_factory=lambda: _int("PREDICT_EVERY_SEC", 1))
    # |future_return| below this = FLAT.  0.0002 = 0.02%
    flat_threshold: float = field(default_factory=lambda: _float("FLAT_THRESHOLD", 0.0002))
    # "mid" = (bid+ask)/2 (recommended, no bid/ask bounce) or "last" = last trade price
    price_source: str = field(default_factory=lambda: _env("PRICE_SOURCE", "mid"))
    # P(up) >= this or <= 1-this counts as "high confidence"
    high_conf_prob: float = field(default_factory=lambda: _float("HIGH_CONF_PROB", 0.80))
    warmup_sec: int = field(default_factory=lambda: _int("WARMUP_SEC", 30))

    # --- Jev (TypeSafe AI) ---
    jev_api_key: str = field(default_factory=lambda: _env("JEV_API_KEY", ""), repr=False)
    jev_base_url: str = field(default_factory=lambda: _env("JEV_BASE_URL", "https://api.typesafe.ai"))
    jev_model: str = field(default_factory=lambda: _env("JEV_MODEL", "jev-latest"))
    jev_timeout_sec: float = field(default_factory=lambda: _float("JEV_TIMEOUT_SEC", 3.0))
    jev_max_retries: int = field(default_factory=lambda: _int("JEV_MAX_RETRIES", 1))
    jev_max_calls_per_sec: float = field(default_factory=lambda: _float("JEV_MAX_CALLS_PER_SEC", 5.0))
    jev_max_inflight: int = field(default_factory=lambda: _int("JEV_MAX_INFLIGHT", 4))
    # USD per 1M tokens. TODO(verify): check current prices on the official pricing page.
    jev_cost_per_m_input: float = field(default_factory=lambda: _float("JEV_COST_PER_M_INPUT", 0.042))
    jev_cost_per_m_output: float = field(default_factory=lambda: _float("JEV_COST_PER_M_OUTPUT", 0.0))
    # 1 = use a fake random predictor (no API key, no cost). Good for testing the pipeline.
    jev_mock: bool = field(default_factory=lambda: _bool("JEV_MOCK", False))

    # --- Storage / logs ---
    db_path: str = field(default_factory=lambda: _env("DB_PATH", str(BASE_DIR / "data" / "jev_btc.db")))
    log_path: str = field(default_factory=lambda: _env("LOG_PATH", str(BASE_DIR / "data" / "app.log")))

    def public_dict(self) -> dict:
        """Config without secrets, saved with each run for reproducibility."""
        d = asdict(self)
        d.pop("jev_api_key", None)
        return d


def load_config() -> Config:
    cfg = Config()
    if cfg.price_source not in ("mid", "last"):
        raise ValueError("PRICE_SOURCE must be 'mid' or 'last'")
    if cfg.predict_every_sec < 1:
        raise ValueError("PREDICT_EVERY_SEC must be >= 1")
    Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(cfg.log_path).parent.mkdir(parents=True, exist_ok=True)
    return cfg
