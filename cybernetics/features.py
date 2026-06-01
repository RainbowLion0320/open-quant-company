"""Regime feature construction for HMM observation vectors.

Builds a 12-dimensional feature set from index data, market breadth,
and volume snapshots. 8 dimensions are used as HMM observations;
the original 4 are preserved for interpretability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from cybernetics.regime_scoring import breadth_strength, clamp, volume_strength

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The 8 HMM observation columns (standardised before feeding to HMM).
OBSERVATION_COLUMNS: list[str] = [
    "return_1d",
    "realized_vol_20d",
    "skewness_20d",
    "kurtosis_20d",
    "drawdown_from_peak",
    "volume_surprise",
    "breadth_momentum",
    "correlation_stock_bond",
]

# The 4 original rule-based features kept for interpretability.
LEGACY_COLUMNS: list[str] = [
    "trend_raw",
    "breadth_raw",
    "risk_raw",
    "volume_raw",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RegimeFeatureSet:
    """Single-day feature vector for regime detection."""

    date: str

    # -- Original 4 (interpretability, not fed to HMM) --
    trend_raw: float = 0.5
    breadth_raw: float = 0.5
    risk_raw: float = 0.5
    volume_raw: float = 0.5

    # -- HMM observations (raw, before standardisation) --
    return_1d: float = 0.0
    realized_vol_20d: float = 0.20
    skewness_20d: float = 0.0
    kurtosis_20d: float = 3.0
    drawdown_from_peak: float = 0.0
    volume_surprise: float = 0.0
    breadth_momentum: float = 0.0
    correlation_stock_bond: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {col: getattr(self, col) for col in LEGACY_COLUMNS + OBSERVATION_COLUMNS}


# ---------------------------------------------------------------------------
# Rolling statistics helpers
# ---------------------------------------------------------------------------

def _rolling_zscore(series: pd.Series, window: int = 252, min_periods: int = 60) -> pd.Series:
    """Rolling z-score standardisation."""
    mu = series.rolling(window, min_periods=min_periods).mean()
    sigma = series.rolling(window, min_periods=min_periods).std().replace(0, 1)
    sigma = sigma.replace(0, 1)
    return ((series - mu) / sigma).clip(-5, 5)  # clip extreme values


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    """Safe division returning 0 where denominator is 0."""
    return (a / b.replace(0, np.nan)).fillna(0.0)


# ---------------------------------------------------------------------------
# Per-index feature extraction
# ---------------------------------------------------------------------------

def _extract_index_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract raw features from a single index OHLCV DataFrame.

    Expects columns: close, volume, amount (optional).
    Returns a DataFrame with date index and feature columns.
    """
    data = df.copy()
    if "close" not in data.columns:
        return pd.DataFrame()

    close = data["close"].astype(float)
    volume = data.get("volume", pd.Series(0.0, index=data.index)).astype(float)
    amount = data.get("amount", volume * close).astype(float)

    ret = close.pct_change()

    features = pd.DataFrame(index=data.index)
    features["return_1d"] = ret
    features["realized_vol_20d"] = ret.rolling(20, min_periods=10).std() * np.sqrt(252)
    features["skewness_20d"] = ret.rolling(20, min_periods=15).skew()
    features["kurtosis_20d"] = ret.rolling(20, min_periods=15).kurt()

    # Drawdown from 60-day peak
    rolling_peak = close.rolling(60, min_periods=20).max()
    features["drawdown_from_peak"] = (close / rolling_peak - 1.0).fillna(0.0)

    # Volume surprise: (today - 20d_mean) / 20d_std
    vol_mean = volume.rolling(20, min_periods=10).mean()
    vol_std = volume.rolling(20, min_periods=10).std().replace(0, 1)
    features["volume_surprise"] = ((volume - vol_mean) / vol_std).fillna(0.0).clip(-5, 5)

    # Amount ratio 5d/20d
    amount_5d = amount.rolling(5, min_periods=3).mean()
    amount_20d = amount.rolling(20, min_periods=10).mean()
    features["amount_ratio_5_20"] = _safe_div(amount_5d, amount_20d)

    # MA alignment for trend
    ma20 = close.rolling(20, min_periods=20).mean()
    ma60 = close.rolling(60, min_periods=60).mean()
    ma120 = close.rolling(120, min_periods=120).mean()

    ret20 = close.pct_change(20)
    ret60 = close.pct_change(60)

    features["trend_raw"] = (
        0.25 * (close > ma20).astype(float)
        + 0.25 * (ma20 > ma60).astype(float)
        + 0.20 * (ma60 > ma120).astype(float)
        + 0.15 * (0.5 + (ret20 / 0.12)).map(clamp)
        + 0.15 * (0.5 + (ret60 / 0.25)).map(clamp)
    )

    # Risk raw
    realized_vol = features["realized_vol_20d"]
    vol_score = 1.0 - ((realized_vol - 0.12) / 0.28).map(clamp)
    dd_score = 1.0 - (features["drawdown_from_peak"].clip(upper=0).abs() / 0.15).map(clamp)
    features["risk_raw"] = (0.60 * dd_score + 0.40 * vol_score).map(clamp)

    return features


# ---------------------------------------------------------------------------
# Bond correlation (optional)
# ---------------------------------------------------------------------------


def load_bond_returns() -> pd.Series | None:
    """Load 10Y treasury bond daily returns from local parquet.

    Returns a pd.Series indexed by date, or None if data unavailable.
    Uses the same synthetic return formula as research/regime_training.py.
    """
    from pathlib import Path

    path = Path("data/store/bond/treasury_yields.parquet")
    if not path.exists():
        return None
    try:
        import pyarrow.parquet as pq
        frame = pq.read_table(path).to_pandas()
    except Exception:
        return None

    if frame.empty:
        return None

    # Find the 10Y yield column
    yld_col = None
    for candidate in ["中国国债收益率10年", "cn10y", "10y"]:
        if candidate in frame.columns:
            yld_col = candidate
            break
    if yld_col is None:
        return None

    # Parse dates
    if "date" in frame.columns:
        dates = pd.to_datetime(frame["date"], errors="coerce")
    elif "日期" in frame.columns:
        dates = pd.to_datetime(frame["日期"], errors="coerce")
    else:
        dates = pd.to_datetime(frame.index, errors="coerce")

    yld = pd.to_numeric(frame[yld_col], errors="coerce")
    proxy = pd.DataFrame({"date": dates.values, "yield": yld.values}).dropna().sort_values("date")
    if proxy.empty:
        return None

    rate = proxy["yield"] / 100.0
    duration = 7.0
    daily_return = (rate.shift(1).fillna(rate) / 252.0) - duration * rate.diff().fillna(0.0)
    daily_return = daily_return.clip(-0.03, 0.03).fillna(0.0)
    daily_return.index = pd.to_datetime(proxy["date"])
    return daily_return

def _compute_stock_bond_correlation(
    equity_returns: pd.Series,
    bond_returns: pd.Series | None,
    window: int = 60,
) -> pd.Series:
    """60-day rolling correlation between equity and bond returns."""
    if bond_returns is None or bond_returns.empty:
        return pd.Series(0.0, index=equity_returns.index)
    aligned = pd.concat([equity_returns, bond_returns], axis=1, sort=False).dropna()
    if aligned.empty or aligned.shape[1] < 2:
        return pd.Series(0.0, index=equity_returns.index)
    corr = aligned.iloc[:, 0].rolling(window, min_periods=20).corr(aligned.iloc[:, 1])
    return corr.reindex(equity_returns.index).fillna(0.0)


# ---------------------------------------------------------------------------
# Main feature builder
# ---------------------------------------------------------------------------

def build_regime_features(
    index_frames: dict[str, pd.DataFrame],
    breadth_raw: float = 0.5,
    breadth_above_ma20: float = 0.5,
    breadth_above_ma60: float = 0.5,
    breadth_above_ma120: float = 0.5,
    amount_ratio_5_20: float = 1.0,
    advance_ratio: float = 0.5,
    up_amount_ratio: float = 0.5,
    sample_size: int = 0,
    bond_returns: pd.Series | None = None,
) -> pd.DataFrame:
    """Build the full feature DataFrame from index data and breadth info.

    Parameters
    ----------
    index_frames : dict mapping symbol → DataFrame (with close, volume, amount)
    breadth_* : market breadth metrics from MarketBreadth or proxy
    bond_returns : optional bond return series for correlation feature

    Returns
    -------
    DataFrame indexed by date with columns LEGACY_COLUMNS + OBSERVATION_COLUMNS.
    """
    # Use Shanghai Composite as primary
    bench = index_frames.get("sh000001")
    if bench is None or bench.empty:
        return pd.DataFrame()

    # Normalize columns
    data = bench.copy()
    cols_lower = {str(c).lower(): c for c in data.columns}
    if "close" not in cols_lower:
        return pd.DataFrame()

    close_col = cols_lower["close"]
    data = data.rename(columns={close_col: "close"})
    if "volume" not in data.columns:
        vol_col = cols_lower.get("volume", cols_lower.get("vol"))
        if vol_col:
            data = data.rename(columns={vol_col: "volume"})
        else:
            data["volume"] = 0.0
    if "amount" not in data.columns:
        data["amount"] = data["volume"] * data["close"]

    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data = data.dropna(subset=["date"]).set_index("date")
    elif "trade_date" in data.columns:
        data["date"] = pd.to_datetime(data["trade_date"], errors="coerce")
        data = data.dropna(subset=["date"]).set_index("date")
    else:
        data.index = pd.to_datetime(data.index, errors="coerce")

    data = data.sort_index()
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce").fillna(0.0)
    data["amount"] = pd.to_numeric(data["amount"], errors="coerce").fillna(data["volume"] * data["close"])
    data = data.dropna(subset=["close"])

    if len(data) < 130:
        return pd.DataFrame()

    # Extract per-index features
    feat = _extract_index_features(data)
    if feat.empty:
        return pd.DataFrame()

    # Compute breadth_raw as a rolling time series from index data.
    # The scalar breadth_* parameters are the latest snapshot; for HMM features
    # we need a historical series so that breadth_momentum = diff(5) has real variation.
    close = data["close"].astype(float)
    ret = close.pct_change()
    ma20 = close.rolling(20, min_periods=20).mean()
    ma60 = close.rolling(60, min_periods=60).mean()
    ma120 = close.rolling(120, min_periods=120).mean()

    # Rolling proxies for breadth components
    rolling_advance = (ret > 0).astype(float).rolling(5, min_periods=3).mean()
    rolling_above_ma20 = (close > ma20).astype(float)
    rolling_above_ma60 = (close > ma60).astype(float)
    rolling_above_ma120 = (close > ma120).astype(float)

    feat["breadth_raw"] = (
        0.35 * rolling_advance
        + 0.30 * rolling_above_ma20
        + 0.25 * rolling_above_ma60
        + 0.10 * rolling_above_ma120
    ).fillna(0.0)

    # Volume raw from volume_strength
    vol_value, _vol_label, _vol_detail = volume_strength(
        amount_ratio_5_20=amount_ratio_5_20,
        advance_ratio=advance_ratio,
        up_amount_ratio=up_amount_ratio,
        index_volume=feat["amount_ratio_5_20"].iloc[-1] if "amount_ratio_5_20" in feat.columns else 1.0,
        sample_size=sample_size,
    )
    # Use the last value as a constant for the series, or compute per-row
    feat["volume_raw"] = feat["amount_ratio_5_20"].apply(
        lambda x: clamp(0.5 + (x - 1.0) * 0.5)
    )

    # Breadth momentum: 5-day change in breadth_raw
    feat["breadth_momentum"] = feat["breadth_raw"].diff(5).fillna(0.0)

    # Stock-bond correlation
    equity_ret = feat["return_1d"]
    feat["correlation_stock_bond"] = _compute_stock_bond_correlation(equity_ret, bond_returns)

    # Select final columns
    all_cols = LEGACY_COLUMNS + OBSERVATION_COLUMNS
    for col in all_cols:
        if col not in feat.columns:
            feat[col] = 0.0

    result = feat[all_cols].copy()
    result = result.replace([np.inf, -np.inf], np.nan)

    # Forward-fill then drop leading NaN
    result = result.ffill().dropna(subset=["return_1d", "realized_vol_20d"])

    # Add date as column
    result["date"] = result.index.strftime("%Y-%m-%d")

    return result


def build_observation_frame(
    features: pd.DataFrame,
    columns: list[str] | None = None,
    standardise: bool = True,
    window: int = 252,
) -> pd.DataFrame:
    """Return the exact feature rows used as HMM observations.

    Keeping the row index with the standardised matrix prevents forward-return
    labels and evaluation series from drifting after rolling z-score drops.
    """
    cols = columns or OBSERVATION_COLUMNS
    available = [c for c in cols if c in features.columns]
    if not available:
        return pd.DataFrame()

    data = features[available].copy()

    if standardise:
        for col in available:
            data[col] = _rolling_zscore(data[col], window=window, min_periods=60)

    return data.dropna()


def build_observation_matrix(
    features: pd.DataFrame,
    columns: list[str] | None = None,
    standardise: bool = True,
    window: int = 252,
    n_components: int | None = None,
) -> tuple[np.ndarray, object | None]:
    """Extract the HMM observation matrix from a feature DataFrame.

    Parameters
    ----------
    features : output of build_regime_features()
    columns : which columns to use (default: OBSERVATION_COLUMNS)
    standardise : whether to apply rolling z-score
    window : rolling window for standardisation
    n_components : if set, apply PCA to reduce to this many components.
                   Prevents any single feature from dominating state assignment.

    Returns
    -------
    (np.ndarray of shape (n_samples, n_features), fitted PCA object or None)
    """
    data = build_observation_frame(features, columns=columns, standardise=standardise, window=window)
    if data.empty:
        return np.array([]), None

    X = data.values

    if n_components is not None:
        if n_components < 1:
            raise ValueError("n_components must be positive")
        if n_components > min(X.shape):
            raise ValueError("n_components cannot exceed min(n_samples, n_features)")
        if n_components >= X.shape[1]:
            return X, None

        from sklearn.decomposition import PCA
        pca = PCA(n_components=n_components, whiten=True)
        X = pca.fit_transform(X)
        return X, pca

    return X, None


def build_feature_index(features: pd.DataFrame) -> pd.DatetimeIndex:
    """Return the DatetimeIndex of a feature DataFrame."""
    if "date" in features.columns:
        return pd.to_datetime(features["date"])
    return pd.DatetimeIndex(features.index)
