"""Market regime score composition and classification helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional

from cybernetics.config import _detection_config
from cybernetics.regime import MarketRegime
from cybernetics.regime_policy import PRODUCTION_REGIME_POLICY
from cybernetics.regime_scoring import classify_regime_value, compose_regime_score
from cybernetics.types import MarketBreadth, MarketVolume
from cybernetics.observations.breadth import _breadth_strength
from cybernetics.observations.trend_risk import _compute_multi_index_trend, _compute_risk_strength
from cybernetics.observations.volume import _compute_full_market_volume, _compute_volume_strength

def _compute_regime_score_v2(
    bench_df,
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
    market_volume: Optional[MarketVolume] = None,
) -> tuple[float, Dict[str, float]]:
    """Compute validated regime score using configured component weights."""
    trend_raw, index_trend = _compute_multi_index_trend(index_frames)
    risk_raw, risk_detail = _compute_risk_strength(index_frames, breadth)
    volume_snapshot = market_volume or _compute_full_market_volume()
    volume_raw, _volume_trend, volume_detail = _compute_volume_strength(index_frames, breadth, volume_snapshot)
    breadth_raw = _breadth_strength(breadth)

    return compose_regime_score(
        trend_raw=trend_raw,
        breadth_raw=breadth_raw,
        risk_raw=risk_raw,
        volume_raw=volume_raw,
        sample_size=breadth.sample_size,
        index_trend=index_trend,
        risk_detail=risk_detail,
        volume_detail=volume_detail,
    )

def _classify_regime(score: float, components: Dict[str, float], breadth: MarketBreadth) -> MarketRegime:
    try:
        det_cfg = _detection_config()
        bull_threshold = float(det_cfg.get("regime_bull_threshold", PRODUCTION_REGIME_POLICY.bull_threshold))
        bear_threshold = float(det_cfg.get("regime_bear_threshold", PRODUCTION_REGIME_POLICY.bear_threshold))
        trend_bull = float(det_cfg.get("regime_trend_confirm", PRODUCTION_REGIME_POLICY.trend_confirm))
        trend_bear = float(det_cfg.get("regime_bear_trend_breakdown", PRODUCTION_REGIME_POLICY.bear_trend_breakdown))
        breadth_bull = float(det_cfg.get("breadth_bull_threshold", PRODUCTION_REGIME_POLICY.breadth_confirm))
        breadth_bear = float(det_cfg.get("breadth_bear_threshold", PRODUCTION_REGIME_POLICY.bear_breadth_breakdown))
    except Exception:
        bull_threshold = PRODUCTION_REGIME_POLICY.bull_threshold
        bear_threshold = PRODUCTION_REGIME_POLICY.bear_threshold
        trend_bull = PRODUCTION_REGIME_POLICY.trend_confirm
        trend_bear = PRODUCTION_REGIME_POLICY.bear_trend_breakdown
        breadth_bull = PRODUCTION_REGIME_POLICY.breadth_confirm
        breadth_bear = PRODUCTION_REGIME_POLICY.bear_breadth_breakdown

    trend_raw = components.get("trend_raw", 0.5)
    breadth_raw = components.get("breadth_raw", _breadth_strength(breadth))

    return MarketRegime(
        classify_regime_value(
            score,
            trend_raw=trend_raw,
            breadth_raw=breadth_raw,
            advance_ratio=breadth.advance_ratio,
            bull_threshold=bull_threshold,
            bear_threshold=bear_threshold,
            trend_bull=trend_bull,
            trend_bear=trend_bear,
            breadth_bull=breadth_bull,
            breadth_bear=breadth_bear,
        )
    )
