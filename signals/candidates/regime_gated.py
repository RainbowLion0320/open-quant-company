"""Candidate regime-gated strategy blend."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from signals.candidates.common import build_signal_row, selected_candidate_rows
from signals.candidates import low_vol_defensive, quality_value, rps_relative_strength, trend_following
from signals.candidates.params import candidate_strategy_params


def _current_regime() -> tuple[str, dict[str, float]]:
    """Return (regime_string, regime_probs)."""
    try:
        from cybernetics.orchestrator import QuantOrchestrator

        snapshot = QuantOrchestrator().detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, "value") else str(snapshot.regime)
        regime = regime if regime in {"bull", "bear", "sideways"} else "sideways"
        probs = getattr(snapshot, "regime_probs", {})
        return regime, probs if probs else {regime: 1.0}
    except Exception:
        return "sideways", {"sideways": 1.0}


def _merge_rows(weighted_sources: Iterable[tuple[str, float, list[dict]]], regime: str) -> list[dict]:
    scores: dict[str, float] = defaultdict(float)
    weights: dict[str, float] = defaultdict(float)
    meta: dict[str, dict] = {}
    details: dict[str, dict] = defaultdict(dict)

    for source_name, weight, rows in weighted_sources:
        for row in rows:
            symbol = row.get("symbol", "")
            if not symbol:
                continue
            scores[symbol] += float(row.get("score", 0.0)) * weight
            weights[symbol] += weight
            meta.setdefault(
                symbol,
                {
                    "name": row.get("name", symbol),
                    "industry": row.get("industry", ""),
                },
            )
            details[symbol][source_name] = {
                "score": row.get("score", 0.0),
                "signal": row.get("signal", "hold"),
            }

    merged: list[dict] = []
    for symbol, weighted_score in scores.items():
        total_weight = weights[symbol] or 1.0
        merged.append(
            build_signal_row(
                symbol=symbol,
                name=meta[symbol]["name"],
                industry=meta[symbol]["industry"],
                score=weighted_score / total_weight,
                signal="hold",
                detail={
                    "strategy": "regime_gated",
                    "regime": regime,
                    "source_scores": details[symbol],
                },
            )
        )
    return merged


def compute(limit: int = 0) -> list[dict]:
    params = candidate_strategy_params("regime_gated")
    regime_weights = params["regime_weights"]
    regime, probs = _current_regime()

    strategy_weights: dict[str, float] = {}
    for regime_name, regime_strategy_weights in regime_weights.items():
        if not isinstance(regime_strategy_weights, Mapping):
            continue
        probability = float(probs.get(regime_name, 0.0))
        for strat_name, strat_weight in regime_strategy_weights.items():
            strategy_weights[strat_name] = strategy_weights.get(strat_name, 0.0) + probability * float(strat_weight)

    strategy_fns = {
        "trend_following": trend_following.compute,
        "rps_relative_strength": rps_relative_strength.compute,
        "quality_value": quality_value.compute,
        "low_vol_defensive": low_vol_defensive.compute,
    }

    weighted_sources = []
    min_active_weight = float(params["min_active_weight"])
    for strat_name, weight in strategy_weights.items():
        if weight > min_active_weight:
            fn = strategy_fns.get(strat_name)
            if fn:
                weighted_sources.append((strat_name, weight, fn(limit=limit)))

    if not weighted_sources:
        sideways_weights = regime_weights.get("sideways", {})
        weighted_sources = [
            (strat_name, float(weight), strategy_fns[strat_name](limit=limit))
            for strat_name, weight in sideways_weights.items()
            if strat_name in strategy_fns and float(weight) > min_active_weight
        ]

    rows = _merge_rows(weighted_sources, regime)

    bear_prob = probs.get("bear", 0.0)
    if bear_prob > float(params["bear_cash_probability_threshold"]):
        cash_row = build_signal_row(
            symbol="CASH",
            name="现金防御代理",
            industry="防御资产",
            score=float(params["cash_score"]) * bear_prob,
            signal="hold",
            detail={"strategy": "regime_gated", "regime": regime, "role": "cash_defense_proxy"},
        )
        rows = [cash_row] + rows

    max_buys = int(params["bear_max_buys"] if regime == "bear" else params["normal_max_buys"])
    return selected_candidate_rows(
        rows,
        "regime_gated",
        selection_overrides={"max_buys": max_buys},
    )
