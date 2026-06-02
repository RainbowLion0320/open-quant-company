"""Regime policy definitions and candidate generation."""
from __future__ import annotations

from typing import Sequence

import pandas as pd

from cybernetics.regime_policy import PRODUCTION_REGIME_POLICY
from research.regime_types import RegimePolicy

CHAMPION_POLICY = RegimePolicy(
    candidate_id="champion_current_formula",
    weights=PRODUCTION_REGIME_POLICY.normalized_weights,
    bull_threshold=PRODUCTION_REGIME_POLICY.bull_threshold,
    bear_threshold=PRODUCTION_REGIME_POLICY.bear_threshold,
    trend_confirm=PRODUCTION_REGIME_POLICY.trend_confirm,
    breadth_confirm=PRODUCTION_REGIME_POLICY.breadth_confirm,
    bear_trend_breakdown=PRODUCTION_REGIME_POLICY.bear_trend_breakdown,
    bear_breadth_breakdown=PRODUCTION_REGIME_POLICY.bear_breadth_breakdown,
    min_dwell=PRODUCTION_REGIME_POLICY.min_dwell,
    smoothing_window=1,
    complexity=1,
)

TREND_ONLY_POLICY = RegimePolicy(
    candidate_id="trend_only_baseline",
    weights={"trend": 1.0, "breadth": 0.0, "risk": 0.0, "volume": 0.0},
    complexity=1,
)

TREND_BREADTH_POLICY = RegimePolicy(
    candidate_id="trend_breadth_baseline",
    weights={"trend": 0.55, "breadth": 0.45, "risk": 0.0, "volume": 0.0},
    complexity=1,
)

BASELINE_IDS = {TREND_ONLY_POLICY.candidate_id, TREND_BREADTH_POLICY.candidate_id}

DEFAULT_EXPOSURE_MAP = {
    "risk_on": {"equity": 0.80, "defensive": 0.20},
    "neutral": {"equity": 0.40, "defensive": 0.60},
    "risk_off": {"equity": 0.10, "defensive": 0.90},
}

PROFIT_REQUIRED_BASELINES = {
    "buy_and_hold_equity",
    "fixed_60_40",
    "ma_20_60_timing",
}

PROFIT_BASELINE_NAMES = [
    "buy_and_hold_equity",
    "fixed_80_20",
    "fixed_60_40",
    "fixed_40_60",
    "cash_only",
    "ma_20_60_timing",
    "ma_60_120_timing",
    "trend_only_regime",
    "trend_breadth_regime",
    "current_champion_formula",
    "best_challenger",
]

def _smooth(series: pd.Series, window: int) -> pd.Series:
    if window <= 1:
        return series
    return series.rolling(window, min_periods=1).mean()


def _enforce_min_dwell(raw_regimes: Sequence[str], min_dwell: int) -> list[str]:
    if min_dwell <= 1 or not raw_regimes:
        return list(raw_regimes)

    current = raw_regimes[0]
    output = [current]
    pending: str | None = None
    pending_start = 0
    pending_count = 0

    for pos, regime in enumerate(raw_regimes[1:], start=1):
        if regime == current:
            pending = None
            pending_count = 0
            output.append(current)
            continue

        if regime != pending:
            pending = regime
            pending_start = pos
            pending_count = 1
            output.append(current)
            continue

        pending_count += 1
        output.append(current)
        if pending_count >= min_dwell:
            current = regime
            for backfill_pos in range(pending_start, pos + 1):
                output[backfill_pos] = current
            pending = None
            pending_count = 0

    return output


def apply_policy(features: pd.DataFrame, policy: RegimePolicy) -> pd.DataFrame:
    """Apply an interpretable regime policy to historical feature rows."""
    data = features.sort_index().copy()
    trend = _smooth(data["trend_raw"].astype(float), policy.smoothing_window)
    breadth = _smooth(data["breadth_raw"].astype(float), policy.smoothing_window)
    risk = _smooth(data["risk_raw"].astype(float), policy.smoothing_window)
    volume = _smooth(data["volume_raw"].astype(float), policy.smoothing_window)
    score = (
        trend * policy.weights.get("trend", 0.0)
        + breadth * policy.weights.get("breadth", 0.0)
        + risk * policy.weights.get("risk", 0.0)
        + volume * policy.weights.get("volume", 0.0)
    ) * 100.0

    raw = []
    for idx, value in score.items():
        row = data.loc[idx]
        if (
            value >= policy.bull_threshold
            and trend.loc[idx] >= policy.trend_confirm
            and row.get("advance_ratio", breadth.loc[idx]) >= policy.breadth_confirm
        ):
            raw.append("bull")
        elif (
            value <= policy.bear_threshold
            or (trend.loc[idx] <= policy.bear_trend_breakdown and breadth.loc[idx] <= policy.bear_breadth_breakdown)
        ):
            raw.append("bear")
        else:
            raw.append("sideways")

    regimes = _enforce_min_dwell(raw, policy.min_dwell)
    return pd.DataFrame({"score": score.round(2), "regime": regimes}, index=data.index)


def generate_candidate_policies(max_candidates: int = 500) -> list[RegimePolicy]:
    weight_sets = [
        {"trend": 1.0, "breadth": 0.0, "risk": 0.0, "volume": 0.0},
        {"trend": 0.55, "breadth": 0.45, "risk": 0.0, "volume": 0.0},
        {"trend": 0.35, "breadth": 0.35, "risk": 0.20, "volume": 0.10},
        {"trend": 0.30, "breadth": 0.40, "risk": 0.20, "volume": 0.10},
        {"trend": 0.30, "breadth": 0.30, "risk": 0.30, "volume": 0.10},
        {"trend": 0.25, "breadth": 0.45, "risk": 0.20, "volume": 0.10},
        {"trend": 0.40, "breadth": 0.25, "risk": 0.25, "volume": 0.10},
    ]
    bull_thresholds = [60.0, 65.0, 70.0]
    bear_thresholds = [30.0, 35.0, 40.0]
    smoothing_windows = [1, 3, 5, 10]
    min_dwells = [1, 3, 5, 20]
    policies = [TREND_ONLY_POLICY, TREND_BREADTH_POLICY]
    seen = {policy.candidate_id for policy in policies}
    for weights in weight_sets:
        for bull in bull_thresholds:
            for bear in bear_thresholds:
                for smoothing in smoothing_windows:
                    for dwell in min_dwells:
                        candidate_id = f"w{len(seen):04d}"
                        if candidate_id in seen:
                            continue
                        policies.append(
                            RegimePolicy(
                                candidate_id=candidate_id,
                                weights=weights,
                                bull_threshold=bull,
                                bear_threshold=bear,
                                smoothing_window=smoothing,
                                min_dwell=dwell,
                                complexity=(1 if smoothing == 1 else 2) + (1 if dwell == 1 else 2),
                            )
                        )
                        seen.add(candidate_id)
                        if len(policies) >= max_candidates:
                            return policies
    return policies


def stability_stats(regimes: pd.Series) -> dict[str, float]:
    regimes = regimes.dropna()
    if regimes.empty:
        return {"turnovers": 0.0, "avg_dwell": 0.0, "bull_ratio": 0.0, "bear_ratio": 0.0, "sideways_ratio": 0.0}
    changes = regimes.ne(regimes.shift()).sum() - 1
    counts = regimes.value_counts(normalize=True)
    runs = regimes.groupby(regimes.ne(regimes.shift()).cumsum()).size()
    return {
        "turnovers": float(max(changes, 0)),
        "avg_dwell": float(runs.mean()) if len(runs) else 0.0,
        "bull_ratio": float(counts.get("bull", 0.0)),
        "bear_ratio": float(counts.get("bear", 0.0)),
        "sideways_ratio": float(counts.get("sideways", 0.0)),
    }


def walk_forward_splits(index: pd.DatetimeIndex, train_years: int = 4, validate_years: int = 1):
    years = sorted(set(index.year))
    for start in range(0, len(years) - train_years - validate_years + 1):
        train = set(years[start : start + train_years])
        validate = set(years[start + train_years : start + train_years + validate_years])
        train_idx = index[index.year.isin(train)]
        validate_idx = index[index.year.isin(validate)]
        if len(train_idx) and len(validate_idx):
            yield train_idx, validate_idx
