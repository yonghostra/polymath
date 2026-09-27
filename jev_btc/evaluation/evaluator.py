"""Accuracy statistics for Jev predictions and the free baselines.

Definitions
  predicted direction : UP if P(up) > 0.5, DOWN if P(up) < 0.5, exactly 0.5 = abstain
  accuracy            : share of correct directions, FLAT outcomes excluded
                        (FLAT = |10s return| < FLAT_THRESHOLD, i.e. too small to matter)
  precision(UP)       : of all UP calls (incl. those that ended FLAT), share that ended UP
  recall(UP)          : of all real UP outcomes, share that were called UP
  signed return       : future_return * (+1 for UP call, -1 for DOWN call), before costs
  p-value             : two-sided test of "accuracy = 50%" (normal approx. to binomial)
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

BASELINES = ["base_momentum", "base_reversal", "base_obi", "base_flow"]


def p_value_vs_coinflip(correct: int, n: int) -> float | None:
    if n == 0:
        return None
    z = (correct - n / 2) / math.sqrt(n / 4)
    return math.erfc(abs(z) / math.sqrt(2))


def direction_metrics(prob: pd.Series, outcome: pd.Series, ret: pd.Series) -> dict:
    df = pd.DataFrame({"p": prob, "o": outcome, "r": ret}).dropna(subset=["p", "o"])
    df = df[df["p"] != 0.5]
    call = np.where(df["p"] > 0.5, "UP", "DOWN")
    n = len(df)
    nf = df["o"] != "FLAT"
    correct_nf = int((call[nf.values] == df["o"][nf].values).sum())
    n_nf = int(nf.sum())

    def prec_rec(label: str) -> tuple[float | None, float | None]:
        called = call == label
        actual = (df["o"] == label).values
        tp = int((called & actual).sum())
        prec = tp / called.sum() if called.sum() else None
        rec = tp / actual.sum() if actual.sum() else None
        return prec, rec

    pu, ru = prec_rec("UP")
    pdn, rdn = prec_rec("DOWN")
    signed = df["r"] * np.where(call == "UP", 1.0, -1.0)
    return {
        "n_calls": n,
        "n_non_flat": n_nf,
        "accuracy": correct_nf / n_nf if n_nf else None,
        "p_value": p_value_vs_coinflip(correct_nf, n_nf),
        "precision_up": pu,
        "recall_up": ru,
        "precision_down": pdn,
        "recall_down": rdn,
        "share_called_up": float((call == "UP").mean()) if n else None,
        "avg_signed_return_bps": float(signed.mean() * 1e4) if n else None,
    }


def evaluate(pred: pd.DataFrame, high_conf_prob: float = 0.8) -> dict:
    """`pred` = Database.labeled_predictions() (one row per labeled Jev prediction)."""
    if pred.empty:
        return {"n": 0}
    out: dict = {"n": len(pred)}
    out["outcome_share"] = pred["outcome"].value_counts(normalize=True).to_dict()
    non_flat = pred[pred["outcome"] != "FLAT"]
    out["base_rate_up"] = float((non_flat["outcome"] == "UP").mean()) if len(non_flat) else None
    out["avg_future_return_bps"] = float(pred["future_return"].mean() * 1e4)
    out["jev"] = direction_metrics(pred["up_probability"], pred["outcome"], pred["future_return"])

    hc = pred[(pred["up_probability"] >= high_conf_prob) | (pred["up_probability"] <= 1 - high_conf_prob)]
    out["high_conf"] = direction_metrics(hc["up_probability"], hc["outcome"], hc["future_return"])
    out["high_conf"]["share_of_all"] = len(hc) / len(pred)

    # Does a higher P(up) go with a higher future return? (rank correlation, -1..1)
    out["spearman_pup_vs_return"] = (
        float(pred["up_probability"].rank().corr(pred["future_return"].rank())) if len(pred) > 2 else None
    )
    return out


def evaluate_baselines(snaps: pd.DataFrame, only_ts: pd.Series | None = None) -> dict:
    """Baseline metrics. If only_ts is given, restricted to the same seconds Jev predicted."""
    df = snaps[snaps["ready"] == 1]
    if only_ts is not None:
        df = df[df["ts"].isin(only_ts)]
    return {b: direction_metrics(df[b], df["outcome"], df["future_return"]) for b in BASELINES}


# ---------------- text report ----------------
def _pct(x) -> str:
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x * 100:.1f}%"


def _num(x, fmt=".3f") -> str:
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else format(x, fmt)


def _row(name: str, m: dict) -> str:
    return (
        f"{name:<16}{m['n_calls']:>8}{m['n_non_flat']:>9}{_pct(m['accuracy']):>8}{_num(m['p_value'], '.4f'):>9}"
        f"{_pct(m['precision_up']):>8}{_pct(m['recall_up']):>8}{_pct(m['precision_down']):>8}"
        f"{_pct(m['recall_down']):>8}{_num(m['avg_signed_return_bps'], '+.3f'):>10}"
    )


def format_report(ev: dict, base: dict, api: dict, cfg) -> str:
    lines = [
        "=" * 96,
        f"Jev {cfg.symbol} {cfg.horizon_sec}s direction test  |  FLAT threshold = {cfg.flat_threshold * 100:.3f}%",
        "=" * 96,
    ]
    if ev.get("n", 0) == 0:
        lines.append("No labeled predictions yet.")
    else:
        lines += [
            f"Labeled predictions : {ev['n']:,}",
            "Outcome share       : " + ", ".join(f"{k} {_pct(v)}" for k, v in sorted(ev["outcome_share"].items())),
            f"Base rate UP (excl. FLAT): {_pct(ev['base_rate_up'])}   <- 'always UP' would get this accuracy",
            f"Avg 10s return      : {_num(ev['avg_future_return_bps'], '+.3f')} bps",
            f"Spearman(P(up), future return): {_num(ev['spearman_pup_vs_return'])}   (>0 = higher P(up) -> higher return)",
            f"High-confidence share (P>={cfg.high_conf_prob:.2f} or <={1 - cfg.high_conf_prob:.2f}): "
            f"{_pct(ev['high_conf']['share_of_all'])}",
            "",
            f"{'model':<16}{'calls':>8}{'nonFLAT':>9}{'acc':>8}{'p-val':>9}{'precUP':>8}{'recUP':>8}"
            f"{'precDN':>8}{'recDN':>8}{'sgnRet':>10}",
            "-" * 96,
            _row("Jev", ev["jev"]),
            _row("Jev high-conf", ev["high_conf"]),
        ]
        for name, m in base.items():
            lines.append(_row(name.replace("base_", "base:"), m))
        lines += [
            "-" * 96,
            "acc = direction accuracy excl. FLAT; p-val < 0.05 = unlikely to be luck;",
            "sgnRet = avg return in the called direction (bps, before fees). Baselines use the same seconds.",
        ]
    lines += [
        "",
        "Jev API cost",
        f"  total calls {api['total_calls']:,} | ok {api['successful_calls']:,} | failed {api['failed_calls']:,} {api['errors'] or ''}",
        f"  avg latency {_num(api['avg_latency_ms'], '.0f')} ms | input tokens {api['input_tokens']:,}",
        f"  estimated cost ${api['estimated_cost_usd']:.4f} | per 1,000 predictions "
        f"${_num(api['cost_per_1000_predictions'], '.4f')}",
        "=" * 96,
    ]
    return "\n".join(lines)
