"""Shared scoring helpers used by live signal generation and backtests."""

from __future__ import annotations

from typing import Any


REGIME_FAVORED_SECTORS: dict[str, tuple[str, ...]] = {
    "bull": ("证券", "电子", "计算机", "电力设备", "国防军工"),
    "bear": ("银行", "公用事业", "交通运输", "食品饮料", "医药生物"),
    "sideways": ("银行", "公用事业", "煤炭", "石油石化", "建筑装饰"),
}


def estimate_buffett_score(inputs: dict[str, Any]) -> float:
    """Estimate a Buffett quality score from recent ROE history."""
    roe_history = list(inputs.get("roe_history") or [])
    recent = roe_history[-5:]
    if not recent:
        return 0.0
    avg_roe = sum(float(v or 0.0) for v in recent) / len(recent)
    return round(min(100.0, max(0.0, avg_roe * 500)), 2)


def favored_sectors_for_regime(regime: str) -> list[str]:
    """Return the canonical sector preference list for a market regime."""
    normalized = str(regime or "sideways").lower()
    return list(REGIME_FAVORED_SECTORS.get(normalized, REGIME_FAVORED_SECTORS["sideways"]))


def score_cybernetic_from_factors(
    industry: str,
    regime: str,
    technical_factors: dict[str, float] | None = None,
) -> float:
    """Score a symbol for the cybernetic sector-rotation strategy."""
    normalized_regime = str(regime or "sideways").lower()
    favored = industry in favored_sectors_for_regime(normalized_regime)
    base = 62.0 if favored else (35.0 if normalized_regime == "bear" else 45.0)
    technical_factors = technical_factors or {}

    trend = float(technical_factors.get("trend_strength", 0.0) or 0.0)
    momentum = float(technical_factors.get("momentum_3m_skip_1m", 0.0) or 0.0)
    volatility = float(technical_factors.get("volatility", 0.30) or 0.30)

    score = base
    score += max(-18.0, min(18.0, trend * 100.0))
    score += max(-12.0, min(12.0, momentum * 80.0))
    score -= max(0.0, (volatility - 0.35) * 45.0)
    if normalized_regime == "bear" and not favored:
        score -= 8.0
    return max(0.0, min(100.0, score))
