"""Rule/HMM regime decision resolution."""
from __future__ import annotations

from typing import Dict

from cybernetics.regime import MarketRegime, to_market_regime
from cybernetics.types import RegimeDecision


def _normalise_regime_probs(regime_probs: Dict[str, float] | None) -> Dict[str, float]:
    probs = {
        "bull": float((regime_probs or {}).get("bull", 0.0) or 0.0),
        "sideways": float((regime_probs or {}).get("sideways", 0.0) or 0.0),
        "bear": float((regime_probs or {}).get("bear", 0.0) or 0.0),
    }
    total = sum(v for v in probs.values() if v > 0)
    if total <= 0:
        return {}
    return {key: max(0.0, value) / total for key, value in probs.items()}


def _resolve_regime_decision(
    *,
    rule_raw_regime: MarketRegime,
    hmm_raw_regime: MarketRegime | None,
    regime_probs: Dict[str, float] | None,
    hmm_confidence: float,
    engine: str,
) -> RegimeDecision:
    """Resolve rule/HMM regime into a single raw decision.

    Hybrid policy:
    - rule/HMM agree: use HMM probabilities directly.
    - disagreement and HMM confidence >= 0.80: trust HMM.
    - disagreement and lower confidence: blend HMM probabilities with a rule vote.
    """
    engine = engine if engine in {"hmm", "hybrid", "rule_based"} else "rule_based"
    rule_raw_regime = to_market_regime(rule_raw_regime)
    probs = _normalise_regime_probs(regime_probs)

    if engine == "rule_based":
        return RegimeDecision(rule_raw_regime, "rule_based", {}, "rule_only")

    if not probs or hmm_raw_regime is None:
        return RegimeDecision(rule_raw_regime, "rule_based", {}, "hmm_unavailable_fallback")

    hmm_raw_regime = to_market_regime(hmm_raw_regime)
    if engine == "hmm":
        return RegimeDecision(hmm_raw_regime, "hmm", probs, "hmm_only")

    if hmm_raw_regime == rule_raw_regime:
        return RegimeDecision(hmm_raw_regime, "hmm", probs, "hmm_rule_consensus")

    from core.settings import get_section
    _hmm_override = float((get_section("cybernetics", {}) or {}).get("hmm_confidence_override", 0.80))
    if hmm_confidence >= _hmm_override:
        return RegimeDecision(hmm_raw_regime, "hmm", probs, "hmm_high_confidence_override")

    rule_weight = min(0.50, max(0.20, 1.0 - hmm_confidence))
    hmm_weight = 1.0 - rule_weight
    blended = {key: value * hmm_weight for key, value in probs.items()}
    blended[rule_raw_regime.value] = blended.get(rule_raw_regime.value, 0.0) + rule_weight
    blended = _normalise_regime_probs(blended)
    raw_regime = MarketRegime(max(blended, key=blended.get)) if blended else rule_raw_regime
    return RegimeDecision(raw_regime, "hybrid", blended, "hybrid_low_confidence_blend")
