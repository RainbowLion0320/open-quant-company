"""Shared scoring helpers used by live signal generation and backtests."""

from __future__ import annotations

from typing import Any


def estimate_buffett_score(inputs: dict[str, Any]) -> float:
    """Estimate a Buffett quality score from recent ROE history."""
    roe_history = list(inputs.get("roe_history") or [])
    recent = roe_history[-5:]
    if not recent:
        return 0.0
    avg_roe = sum(float(v or 0.0) for v in recent) / len(recent)
    return round(min(100.0, max(0.0, avg_roe * 500)), 2)
