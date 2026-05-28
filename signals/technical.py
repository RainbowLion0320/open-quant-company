"""Shared technical factor helpers for live signals, backtests and research scripts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_TECHNICAL_FACTORS: dict[str, float] = {
    "momentum_1m": 0.0,
    "momentum_3m": 0.0,
    "momentum_3m_skip_1m": 0.0,
    "momentum_6m_skip_1m": 0.0,
    "trend_strength": 0.0,
    "volatility": 0.30,
}


def close_series(prices: pd.DataFrame | pd.Series | Iterable[Any]) -> pd.Series:
    """Normalize a price frame/series/list into a numeric close series."""
    if isinstance(prices, pd.DataFrame):
        if "close" not in prices.columns:
            return pd.Series(dtype="float64")
        series = prices["close"]
    else:
        series = pd.Series(prices)
    return pd.to_numeric(series, errors="coerce").dropna()


def close_history(prices: pd.DataFrame | pd.Series | Iterable[Any], idx: int | None = None) -> pd.Series:
    series = close_series(prices)
    if idx is None:
        return series
    return series.iloc[: idx + 1].dropna()


def compute_momentum_periods(
    prices: pd.DataFrame | pd.Series | Iterable[Any],
    periods: Iterable[int],
    *,
    skip_recent: int = 0,
) -> dict[int, float]:
    """Compute point-in-time momentum over each requested period."""
    close = close_series(prices)
    requested = [int(period) for period in periods]
    if not requested:
        return {}
    if len(close) < max(requested) + skip_recent + 1:
        return {period: 0.0 for period in requested}

    result: dict[int, float] = {}
    for period in requested:
        if len(close) < period + skip_recent + 1:
            result[period] = 0.0
            continue
        end_idx = -1 - skip_recent if skip_recent else -1
        start_idx = end_idx - period
        base = float(close.iloc[start_idx])
        result[period] = float(close.iloc[end_idx] / base - 1.0) if base else 0.0
    return result


def annualized_volatility(
    prices: pd.DataFrame | pd.Series | Iterable[Any],
    *,
    window: int = 20,
    periods_per_year: int = 252,
    default: float = 0.30,
) -> float:
    close = close_series(prices)
    if len(close) < window + 1:
        return default
    returns = close.pct_change().dropna().tail(window)
    if returns.empty:
        return default
    return float(returns.std() * np.sqrt(periods_per_year))


def trend_strength(prices: pd.DataFrame | pd.Series | Iterable[Any], *, window: int = 120) -> float:
    close = close_series(prices)
    if len(close) < window:
        return 0.0
    moving_average = float(close.tail(window).mean())
    return float(close.iloc[-1] / moving_average - 1.0) if moving_average else 0.0


def technical_factors_from_series(series: pd.Series, idx: int | None = None) -> dict[str, float]:
    """Compute the canonical technical factor set from point-in-time price history."""
    history = close_history(series, idx)
    if len(history) < 2:
        return dict(DEFAULT_TECHNICAL_FACTORS)

    mom = compute_momentum_periods(history, [21, 63])
    mom_3m_skip = compute_momentum_periods(history, [42], skip_recent=21)
    mom_6m_skip = compute_momentum_periods(history, [105], skip_recent=21)
    return {
        "momentum_1m": mom.get(21, 0.0),
        "momentum_3m": mom.get(63, 0.0),
        "momentum_3m_skip_1m": mom_3m_skip.get(42, 0.0),
        "momentum_6m_skip_1m": mom_6m_skip.get(105, 0.0),
        "trend_strength": trend_strength(history, window=120),
        "volatility": annualized_volatility(history, window=20),
    }


def technical_factors_from_frame(df: pd.DataFrame) -> dict[str, float]:
    return technical_factors_from_series(close_series(df))


def momentum_score(series: pd.Series, dt: Any | None = None) -> float:
    """Momentum plus volatility score used by multi-asset research tournaments."""
    history = close_series(series)
    if dt is not None:
        history = history.loc[:dt].dropna()
    if len(history) < 63:
        return 0.0

    mom_1m = compute_momentum_periods(history, [20]).get(20, 0.0)
    mom_3m = compute_momentum_periods(history, [62]).get(62, 0.0)
    vol = annualized_volatility(history, window=19, default=0.30)
    return float(50.0 + mom_1m * 80.0 + mom_3m * 40.0 - vol * 25.0)
