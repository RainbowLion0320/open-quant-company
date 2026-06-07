"""Shared regime context lookup for signal generation."""

from __future__ import annotations


def current_regime() -> tuple[str, dict[str, float]]:
    """Return the current regime label and probabilities for signal modules."""
    try:
        from cybernetics.orchestrator import QuantOrchestrator

        snapshot = QuantOrchestrator().detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, "value") else str(snapshot.regime)
        regime = regime if regime in {"bull", "bear", "sideways"} else "sideways"
        probs = getattr(snapshot, "regime_probs", {})
        return regime, probs if probs else {regime: 1.0}
    except Exception:
        return "sideways", {"sideways": 1.0}
