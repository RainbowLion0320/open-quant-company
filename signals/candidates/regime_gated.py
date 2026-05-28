"""Candidate regime-gated strategy blend."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from signals.candidates.common import build_signal_row, selected_candidate_rows
from signals.candidates import low_vol_defensive, quality_value, rps_relative_strength, trend_following


def _current_regime() -> str:
    try:
        from cybernetics.orchestrator import QuantOrchestrator

        snapshot = QuantOrchestrator().detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, "value") else str(snapshot.regime)
        return regime if regime in {"bull", "bear", "sideways"} else "sideways"
    except Exception:
        return "sideways"


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
    regime = _current_regime()
    if regime == "bull":
        rows = _merge_rows(
            [
                ("trend_following", 0.55, trend_following.compute(limit=limit)),
                ("rps_relative_strength", 0.45, rps_relative_strength.compute(limit=limit)),
            ],
            regime,
        )
        return selected_candidate_rows(rows, "regime_gated", min_score=55.0, max_buys=20)

    if regime == "bear":
        defensive_rows = low_vol_defensive.compute(limit=limit)
        cash_row = build_signal_row(
            symbol="CASH",
            name="现金防御代理",
            industry="防御资产",
            score=80.0,
            signal="hold",
            detail={"strategy": "regime_gated", "regime": regime, "role": "cash_defense_proxy"},
        )
        rows = [cash_row] + [
            build_signal_row(
                symbol=row["symbol"],
                name=row["name"],
                industry=row.get("industry", ""),
                score=float(row.get("score", 0.0)) * 0.75,
                signal="hold",
                detail={
                    "strategy": "regime_gated",
                    "regime": regime,
                    "source_scores": {"low_vol_defensive": row.get("score", 0.0)},
                },
            )
            for row in defensive_rows
        ]
        return selected_candidate_rows(rows, "regime_gated", min_score=55.0, max_buys=10)

    rows = _merge_rows(
        [
            ("quality_value", 0.55, quality_value.compute(limit=limit)),
            ("low_vol_defensive", 0.45, low_vol_defensive.compute(limit=limit)),
        ],
        regime,
    )
    return selected_candidate_rows(rows, "regime_gated", min_score=55.0, max_buys=20)
