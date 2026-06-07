"""Historical replay helpers for the production Market Regime policy."""

from __future__ import annotations

import pandas as pd

from research.regime.features import build_regime_feature_history
from research.regime.policies import CHAMPION_POLICY, apply_policy


def _benchmark_close_frame(bench_close_series: pd.Series) -> pd.DataFrame:
    series = pd.Series(bench_close_series).dropna()
    frame = pd.DataFrame({
        "date": pd.to_datetime(series.index, errors="coerce"),
        "close": pd.to_numeric(series.values, errors="coerce"),
        "volume": 0.0,
    })
    return frame.dropna(subset=["date", "close"]).sort_values("date")


def build_production_regime_map(bench_close_series: pd.Series) -> dict[str, str]:
    """Replay the production Market Regime policy historically without look-ahead."""
    index_frame = _benchmark_close_frame(bench_close_series)
    if index_frame.empty:
        return {}

    features = build_regime_feature_history(index_frame)
    if features.empty:
        monthly = index_frame.set_index("date")["close"].resample("ME").last().dropna()
        return {dt.strftime("%Y-%m"): "sideways" for dt in monthly.index}

    daily_regime = apply_policy(features, CHAMPION_POLICY)["regime"]
    close = index_frame.set_index("date")["close"]
    monthly = close.resample("ME").last().dropna()
    regimes = {}
    for i in range(len(monthly)):
        key = monthly.index[i].strftime("%Y-%m")
        if i == 0:
            regimes[key] = "sideways"
            continue
        cutoff = monthly.index[i - 1]
        available = daily_regime[daily_regime.index <= cutoff]
        regimes[key] = str(available.iloc[-1]) if len(available) else "sideways"
    return regimes
