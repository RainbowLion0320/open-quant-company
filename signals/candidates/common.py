from __future__ import annotations

import math
from typing import Any

import pandas as pd

from data.fetcher import get_stock_daily
from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_NAME
from signals.selection import apply_ranked_buys


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


def bounded_score(value: Any, default: float = 0.0) -> float:
    return round(max(0.0, min(100.0, safe_float(value, default))), 2)


def is_st_name(name: str) -> bool:
    return "ST" in str(name or "").upper()


def candidate_symbols(limit: int = 0) -> list[str]:
    symbols = list(CIRCLE_STOCKS)
    if limit and limit > 0:
        return symbols[:limit]
    return symbols


def stock_name(symbol: str) -> str:
    return SYMBOL_NAME.get(symbol, symbol)


def stock_industry(symbol: str) -> str:
    return SYMBOL_INDUSTRY.get(symbol, "")


def price_frame(symbol: str, min_rows: int = 2) -> pd.DataFrame:
    df = get_stock_daily(symbol)
    if df is None or df.empty or len(df) < min_rows:
        return pd.DataFrame()

    out = df.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.sort_values("date")
    for col in ("open", "high", "low", "close", "volume", "amount", "turnover"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.dropna(subset=["close"]) if "close" in out.columns else pd.DataFrame()


def close_series(df: pd.DataFrame) -> pd.Series:
    if df is None or df.empty or "close" not in df.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df["close"], errors="coerce").dropna()


def pct_return(close: pd.Series, window: int, *, skip_recent: int = 0) -> float:
    if len(close) < window + skip_recent + 1:
        return 0.0
    end_idx = -1 - skip_recent if skip_recent else -1
    start_idx = end_idx - window
    base = safe_float(close.iloc[start_idx])
    latest = safe_float(close.iloc[end_idx])
    return latest / base - 1.0 if base else 0.0


def moving_average(close: pd.Series, window: int) -> float:
    if len(close) < window:
        return 0.0
    return safe_float(close.tail(window).mean())


def annualized_volatility(close: pd.Series, window: int = 20, default: float = 0.30) -> float:
    if len(close) < window + 1:
        return default
    returns = close.pct_change().dropna().tail(window)
    if returns.empty:
        return default
    return safe_float(returns.std() * math.sqrt(252), default)


def volume_ratio(df: pd.DataFrame, window: int = 20) -> float:
    if df is None or df.empty or "volume" not in df.columns or len(df) < window + 1:
        return 1.0
    volume = pd.to_numeric(df["volume"], errors="coerce").dropna()
    if len(volume) < window + 1:
        return 1.0
    base = safe_float(volume.iloc[-window - 1 : -1].mean(), 1.0)
    return safe_float(volume.iloc[-1], 0.0) / base if base else 1.0


def drawdown_control_score(close: pd.Series, window: int = 60) -> float:
    if len(close) < 2:
        return 0.0
    recent = close.tail(window)
    peak = recent.cummax()
    drawdown = (recent / peak - 1.0).min()
    return bounded_score(100.0 + safe_float(drawdown) * 250.0)


def selected_candidate_rows(
    rows: list[dict],
    strategy: str,
    *,
    min_score: float = 55.0,
    max_buys: int = 20,
) -> list[dict]:
    return apply_ranked_buys(
        rows,
        strategy,
        default_min_score=min_score,
        default_top_pct=0.05,
        default_min_buys=1,
        default_max_buys=max_buys,
    )


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
        "score": bounded_score(score),
        "signal": signal if signal in {"buy", "hold", "sell"} else "hold",
        "detail": detail or {},
    }
