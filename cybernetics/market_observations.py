"""Compatibility facade for market observation helpers."""
from __future__ import annotations

from cybernetics.config import _load_config
from cybernetics.observations import trend_risk as _trend_risk
from cybernetics.observations.sources import (
    _clamp,
    _frame_close_volume,
    _get_regime_indexes,
    _regime_indexes,
    _stock_daily_files,
    _stock_daily_source_sql,
)
from cybernetics.observations.breadth import (
    _breadth_strength,
    _compute_full_market_breadth,
    _compute_full_market_breadth_duckdb,
    _read_breadth_observation,
)
from cybernetics.observations.trend_risk import (
    _compute_multi_index_trend,
    _index_risk_metrics,
    _index_trend_strength,
)
from cybernetics.observations.volume import (
    _compute_full_market_volume,
    _compute_full_market_volume_duckdb,
    _compute_multi_index_volume,
    _compute_volume_strength,
    _index_volume_confirmation,
)
from cybernetics.observations.scoring import _classify_regime, _compute_regime_score_v2
from cybernetics.observations.hmm_detection import _hmm_detect


def _compute_risk_strength(index_frames, breadth):
    overrides = {
        "_load_config": _load_config,
        "_regime_indexes": _regime_indexes,
        "_index_risk_metrics": _index_risk_metrics,
    }
    previous = {name: getattr(_trend_risk, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(_trend_risk, name, value)
        return _trend_risk._compute_risk_strength(index_frames, breadth)
    finally:
        for name, value in previous.items():
            setattr(_trend_risk, name, value)


__all__ = [
    "_breadth_strength",
    "_classify_regime",
    "_clamp",
    "_compute_full_market_breadth",
    "_compute_full_market_breadth_duckdb",
    "_compute_full_market_volume",
    "_compute_full_market_volume_duckdb",
    "_compute_multi_index_trend",
    "_compute_multi_index_volume",
    "_compute_regime_score_v2",
    "_compute_risk_strength",
    "_compute_volume_strength",
    "_frame_close_volume",
    "_get_regime_indexes",
    "_hmm_detect",
    "_index_risk_metrics",
    "_index_trend_strength",
    "_index_volume_confirmation",
    "_load_config",
    "_read_breadth_observation",
    "_regime_indexes",
    "_stock_daily_files",
    "_stock_daily_source_sql",
]
