"""Point-in-time AlphaModel adapters for candidate strategies."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

import pandas as pd

from core.settings import get_dotted, get_settings
from pipeline.alpha import AlphaModel
from pipeline.types import AlphaSignal
from signals.candidates.params import CANDIDATE_STRATEGY_NAMES

from backtest.candidate_alpha_features import register_price_panels, transfer_price_panels
from backtest.candidate_alpha_scorers import score_candidate_strategy


def candidate_backtest_strategy_names() -> tuple[str, ...]:
    return CANDIDATE_STRATEGY_NAMES


def is_candidate_backtest_strategy(name: str) -> bool:
    return name in CANDIDATE_STRATEGY_NAMES


def candidate_selection_config(name: str) -> dict[str, Any]:
    cfg = get_settings()
    global_cfg = cfg.get("signal_selection", {}) if isinstance(cfg, dict) else {}
    strategy_cfg = get_dotted(cfg, f"signal_selection.strategies.{name}", {}) or {}
    merged = {
        "min_score": global_cfg.get("min_score", 50),
        "top_pct": global_cfg.get("top_pct", 0.05),
        "min_buys": global_cfg.get("min_buys", 5),
        "max_buys": global_cfg.get("max_buys", 20),
    }
    if isinstance(strategy_cfg, Mapping):
        merged.update(strategy_cfg)
    return merged


def candidate_max_positions(name: str) -> int:
    return int(candidate_selection_config(name).get("max_buys", 20))


def candidate_min_score(name: str) -> float:
    return float(candidate_selection_config(name).get("min_score", 50))


class CandidateStrategyAlphaModel(AlphaModel):
    """Generate candidate strategy alpha from point-in-time backtest history."""

    def __init__(self, name: str, label: str, min_score: float | None = None):
        self.name = name
        self.label = label
        self.min_score = candidate_min_score(name) if min_score is None else float(min_score)

    def generate_alpha(self, universe: list[str], prices: pd.DataFrame, date_idx: int, regime: str) -> list[AlphaSignal]:
        rows = score_candidate_strategy(self.name, universe, prices, date_idx, regime)
        timestamp = datetime.now().isoformat()
        signals: list[AlphaSignal] = []
        for symbol, row in rows.items():
            score = float(row.get("score", 0.0) or 0.0)
            if score < self.min_score:
                continue
            signals.append(AlphaSignal(
                symbol=symbol,
                strategy=self.name,
                direction="buy" if score >= 50 else "hold",
                confidence=min(1.0, max(0.0, score / 100.0)),
                score=round(score, 1),
                horizon_days=20,
                reason=f"{self.label} score={score:.1f} regime={regime}",
                timestamp=timestamp,
            ))
        signals.sort(key=lambda item: item.score, reverse=True)
        return signals

    def generate_score_panel(self, universe: list[str], prices: pd.DataFrame, date_idx: int, regime: str) -> list[dict]:
        rows = score_candidate_strategy(self.name, universe, prices, date_idx, regime)
        timestamp = datetime.now().isoformat()
        out: list[dict] = []
        for symbol in universe:
            row = rows.get(symbol, {})
            score = row.get("score")
            out.append(
                {
                    "symbol": symbol,
                    "strategy": self.name,
                    "score": float(score) if score is not None else None,
                    "horizon_days": 20,
                    "timestamp": timestamp,
                    "data_quality": "ok" if score is not None else "missing_score",
                }
            )
        return out
