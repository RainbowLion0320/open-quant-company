"""Shared research-time Market Regime policy data structures."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PromotionGateResult(StrEnum):
    KEEP_CHAMPION = "keep_champion"
    RECOMMEND_CHALLENGER_FOR_REVIEW = "recommend_challenger_for_review"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True)
class RegimePolicy:
    candidate_id: str
    weights: dict[str, float]
    bull_threshold: float = 65.0
    bear_threshold: float = 35.0
    trend_confirm: float = 0.55
    breadth_confirm: float = 0.55
    bear_trend_breakdown: float = 0.40
    bear_breadth_breakdown: float = 0.40
    min_dwell: int = 1
    smoothing_window: int = 1
    complexity: int = 1
