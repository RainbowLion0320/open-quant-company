"""
Signal selection helpers.

Raw strategy scores are cross-sectional ranks, not executable orders.  This
module turns a full scored universe into a bounded buy list while preserving
hold rows for observability in Web and history views.
"""
from __future__ import annotations

from math import ceil
from typing import Iterable, List, Mapping

from core.settings import get_settings

DEFAULT_SELECTION = {
    "top_pct": 0.05,
    "min_buys": 5,
    "max_buys": 80,
    "min_score": 50.0,
    "strategies": {},
}


def _load_config() -> dict:
    cfg = get_settings()
    merged = dict(DEFAULT_SELECTION)
    merged.update(cfg.get("signal_selection", {}) or {})
    merged["strategies"] = {
        **DEFAULT_SELECTION["strategies"],
        **(cfg.get("signal_selection", {}).get("strategies", {}) if cfg.get("signal_selection") else {}),
    }
    return merged


def _score(row: dict) -> float:
    try:
        return float(row.get("score", 0.0))
    except Exception:
        return 0.0


def apply_ranked_buys(
    signals: Iterable[dict],
    strategy: str,
    *,
    default_min_score: float = 50.0,
    default_top_pct: float = 0.05,
    default_min_buys: int = 5,
    default_max_buys: int = 80,
    selection_overrides: Mapping[str, float | int] | None = None,
) -> List[dict]:
    """
    Mark only the highest ranked eligible rows as buy and keep all others hold.

    The output is sorted by score descending so downstream paper trading reads
    the strongest candidates first even if it has an order-count risk cap.
    """
    rows = [dict(r) for r in signals]
    if not rows:
        return []

    cfg = _load_config()
    strat_cfg = dict(cfg.get("strategies", {}).get(strategy, {}) or {})
    if selection_overrides:
        strat_cfg.update(dict(selection_overrides))
    min_score = float(strat_cfg.get("min_score", cfg.get("min_score", default_min_score)))
    top_pct = float(strat_cfg.get("top_pct", cfg.get("top_pct", default_top_pct)))
    min_buys = int(strat_cfg.get("min_buys", cfg.get("min_buys", default_min_buys)))
    max_buys = int(strat_cfg.get("max_buys", cfg.get("max_buys", default_max_buys)))

    ranked = sorted(rows, key=_score, reverse=True)
    eligible = [r for r in ranked if _score(r) >= min_score]
    target_n = min(len(eligible), max_buys, max(min_buys, ceil(len(ranked) * top_pct)))
    buy_symbols = {r.get("symbol") for r in eligible[:target_n]}

    for rank, row in enumerate(ranked, 1):
        detail = row.get("detail") or {}
        if not isinstance(detail, dict):
            detail = {"raw_detail": str(detail)}
        detail["selection_rank"] = rank
        detail["selection_min_score"] = min_score
        detail["selection_target_n"] = target_n
        row["detail"] = detail
        row["signal"] = "buy" if row.get("symbol") in buy_symbols else "hold"

    return ranked
