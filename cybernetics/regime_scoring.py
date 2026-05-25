"""Pure scoring helpers for market regime detection.

The orchestrator owns data access and market snapshots; this module keeps the
formula layer deterministic so score changes are easier to test and review.
"""
from __future__ import annotations

import math
from typing import Dict, Mapping, Optional


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    """Clamp a numeric value and treat non-finite inputs as the lower bound."""
    if math.isnan(value) or math.isinf(value):
        return lower
    return min(upper, max(lower, value))


def breadth_strength(
    advance_ratio: float,
    above_ma20: float,
    above_ma60: float,
    above_ma120: float,
) -> float:
    """Return the 0-1 market breadth strength used by regime scoring."""
    return clamp(
        0.35 * advance_ratio
        + 0.30 * above_ma20
        + 0.25 * above_ma60
        + 0.10 * above_ma120
    )


def volume_strength(
    *,
    amount_ratio_5_20: float,
    advance_ratio: float,
    up_amount_ratio: float,
    index_volume: float,
    sample_size: int,
    amount_5d: float = 0.0,
    amount_20d: float = 0.0,
    volume_expansion: float = 1.2,
    volume_contraction: float = 0.8,
    index_detail: Optional[Mapping[str, float]] = None,
) -> tuple[float, str, Dict[str, float]]:
    """Return volume confirmation strength, trend label, and audit details."""
    trend = (
        "放量"
        if amount_ratio_5_20 > volume_expansion
        else ("缩量" if amount_ratio_5_20 < volume_contraction else "正常")
    )

    if advance_ratio >= 0.55:
        market_activity = 0.5 + (amount_ratio_5_20 - 1.0) * 0.7
    elif advance_ratio <= 0.45:
        market_activity = 0.5 - (amount_ratio_5_20 - 1.0) * 0.7
    else:
        market_activity = 0.5 + (amount_ratio_5_20 - 1.0) * 0.2
    market_activity = clamp(market_activity)

    up_amount_score = clamp(up_amount_ratio)
    index_volume_score = clamp(index_volume)
    strength = 0.50 * market_activity + 0.30 * up_amount_score + 0.20 * index_volume_score

    detail = {
        "volume_market_activity_raw": round(market_activity, 4),
        "volume_up_amount_raw": round(up_amount_score, 4),
        "volume_index_raw": round(index_volume_score, 4),
        "amount_ratio_5_20": round(amount_ratio_5_20, 4),
        "up_amount_ratio": round(up_amount_ratio, 4),
        "volume_sample_size": float(sample_size),
        "amount_5d": round(amount_5d, 2),
        "amount_20d": round(amount_20d, 2),
    }
    if index_detail:
        detail.update(index_detail)
    return clamp(strength), trend, detail


def compose_regime_score(
    *,
    trend_raw: float,
    breadth_raw: float,
    risk_raw: float,
    volume_raw: float,
    sample_size: int,
    index_trend: Optional[Mapping[str, float]] = None,
    risk_detail: Optional[Mapping[str, float]] = None,
    volume_detail: Optional[Mapping[str, float]] = None,
) -> tuple[float, Dict[str, float]]:
    """Compose the v2 regime score and return component-level details."""
    components: Dict[str, float] = {
        "trend": round(clamp(trend_raw) * 35.0, 1),
        "breadth": round(clamp(breadth_raw) * 35.0, 1),
        "risk": round(clamp(risk_raw) * 20.0, 1),
        "volume": round(clamp(volume_raw) * 10.0, 1),
        "trend_raw": round(clamp(trend_raw), 4),
        "breadth_raw": round(clamp(breadth_raw), 4),
        "risk_raw": round(clamp(risk_raw), 4),
        "volume_raw": round(clamp(volume_raw), 4),
        "sample_size": float(sample_size),
    }
    if index_trend:
        components.update({f"trend_{symbol}": value for symbol, value in index_trend.items()})
    if risk_detail:
        components.update(risk_detail)
    if volume_detail:
        components.update(volume_detail)

    score = components["trend"] + components["breadth"] + components["risk"] + components["volume"]
    return round(score, 1), components


def classify_regime_value(
    score: float,
    *,
    trend_raw: float,
    breadth_raw: float,
    advance_ratio: float,
    bull_threshold: float = 65.0,
    bear_threshold: float = 35.0,
    breadth_bull: float = 0.55,
    breadth_bear: float = 0.40,
) -> str:
    """Classify a market regime score into bull, sideways, or bear."""
    if score >= bull_threshold and trend_raw >= 0.55 and advance_ratio >= breadth_bull:
        return "bull"
    if score <= bear_threshold or (trend_raw <= 0.40 and breadth_raw <= breadth_bear):
        return "bear"
    return "sideways"
