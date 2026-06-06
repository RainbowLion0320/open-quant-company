"""Shared market regime primitives.

This module is the stable import point for regime enum/normalization and the
lightweight trend detector. The orchestrator can still provide full-context
market snapshots, but scripts and allocators should not depend on it for basic
regime vocabulary.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Mapping


class MarketRegime(Enum):
    """市场状态 — 顶层判断"""

    BULL = "bull"
    SIDEWAYS = "sideways"
    BEAR = "bear"
    UNKNOWN = "unknown"


VALID_REGIMES = {regime.value for regime in MarketRegime}


def normalize_regime(value: Any, default: str = "sideways") -> str:
    """Normalize enum/string regime values to canonical lowercase strings."""
    raw = value.value if isinstance(value, MarketRegime) else str(value or "")
    normalized = raw.lower()
    return normalized if normalized in VALID_REGIMES else default


def to_market_regime(value: Any, default: MarketRegime = MarketRegime.SIDEWAYS) -> MarketRegime:
    """Convert enum/string values to MarketRegime."""
    normalized = normalize_regime(value, default.value)
    return MarketRegime(normalized)


def detect_trend_regime(
    index_data: Mapping[str, Any] | None = None,
    window: int = 60,
    symbol: str = "sh000001",
    fetch_index_daily: Callable[[str], Any] | None = None,
) -> MarketRegime:
    """Detect a lightweight trend regime from a single index close series."""
    if index_data is None or symbol not in index_data:
        try:
            fetcher = fetch_index_daily
            if fetcher is None:
                from data.ingestion.fetcher import get_index_daily
                fetcher = lambda sym: get_index_daily(sym, force_refresh=False)
            df = fetcher(symbol)
        except Exception:
            return MarketRegime.UNKNOWN
    else:
        df = index_data.get(symbol)

    if df is None or len(df) < max(window, 60):
        return MarketRegime.UNKNOWN

    recent = df.tail(window)
    close = recent["close"].values if "close" in df.columns else recent["收盘"].values

    ma5 = close[-5:].mean()
    ma20 = close[-20:].mean()
    ma60 = close[-60:].mean() if len(close) >= 60 else close.mean()
    current = close[-1]

    if current > ma5 > ma20 > ma60:
        return MarketRegime.BULL
    if current < ma5 < ma20 < ma60:
        return MarketRegime.BEAR
    return MarketRegime.SIDEWAYS
