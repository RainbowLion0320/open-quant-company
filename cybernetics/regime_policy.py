"""Canonical production Market Regime policy parameters."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


def _get_score_weights() -> dict[str, float]:
    from core.settings import get_section
    cfg = get_section("cybernetics.score_weights", {}) or {}
    defaults = {"trend": 30.0, "breadth": 30.0, "risk": 30.0, "volume": 10.0}
    return {**defaults, **{k: float(v) for k, v in cfg.items()}}


PRODUCTION_REGIME_SCORE_WEIGHTS = _get_score_weights()


@dataclass(frozen=True)
class ProductionRegimePolicy:
    """Single source of truth for the live Market Regime formula."""

    score_weights: Mapping[str, float] = field(default_factory=lambda: dict(PRODUCTION_REGIME_SCORE_WEIGHTS))
    bull_threshold: float = 60.0
    bear_threshold: float = 40.0
    trend_confirm: float = 0.55
    breadth_confirm: float = 0.55
    bear_trend_breakdown: float = 0.40
    bear_breadth_breakdown: float = 0.40
    min_dwell: int = 3

    @property
    def normalized_weights(self) -> dict[str, float]:
        return {key: value / 100.0 for key, value in self.score_weights.items()}


PRODUCTION_REGIME_POLICY = ProductionRegimePolicy()

