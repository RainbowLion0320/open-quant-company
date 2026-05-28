from __future__ import annotations

import math
from typing import Any

import pandas as pd


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except Exception:
        return default
    return default if math.isnan(number) else number


def percentile_score(values: pd.Series) -> dict[str, float]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {}
    if len(clean) == 1:
        return {str(clean.index[0]): 100.0}
    ranked = clean.rank(method="average", pct=True)
    min_rank = ranked.min()
    max_rank = ranked.max()
    scaled = (ranked - min_rank) / max(max_rank - min_rank, 1e-12) * 100
    return {str(k): round(float(v), 2) for k, v in scaled.items()}


def is_st_name(name: str) -> bool:
    return "ST" in str(name or "").upper()


def build_signal_row(
    symbol: str,
    name: str,
    industry: str,
    score: float,
    signal: str,
    detail: dict | None = None,
) -> dict:
    return {
        "symbol": str(symbol),
        "name": str(name or symbol),
        "industry": str(industry or ""),
        "score": round(safe_float(score), 2),
        "signal": signal if signal in {"buy", "hold", "sell"} else "hold",
        "detail": detail or {},
    }
