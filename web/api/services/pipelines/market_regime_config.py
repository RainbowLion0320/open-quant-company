"""Configuration and formatting helpers for the Market Regime pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from web.api.serializers import safe_float
from web.api.services.pipelines.common import score


DEFAULT_SCORE_WEIGHTS = {"trend": 30.0, "breadth": 30.0, "risk": 30.0, "volume": 10.0}
DEFAULT_BREADTH_WEIGHTS = {"advance_ratio": 0.35, "above_ma20": 0.30, "above_ma60": 0.25, "above_ma120": 0.10}
DEFAULT_RISK_WEIGHTS = {"drawdown": 0.50, "volatility": 0.30, "pressure": 0.20}
DEFAULT_DETECTION = {
    "regime_bull_threshold": 60.0,
    "regime_bear_threshold": 40.0,
    "regime_trend_confirm": 0.55,
    "regime_bear_trend_breakdown": 0.40,
    "breadth_bull_threshold": 0.55,
    "breadth_bear_threshold": 0.40,
    "regime_min_dwell": 3,
    "volume_expansion": 1.20,
    "volume_contraction": 0.80,
}


def resolve_model_path(model_path: object) -> Path:
    path = Path(str(model_path or "data/reference/models/regime_hmm"))
    return path if path.is_absolute() else Path.cwd() / path


def read_model_meta(model_path: Path) -> dict[str, Any]:
    meta_path = model_path / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def configured_numbers(raw: object, defaults: dict[str, float]) -> dict[str, float]:
    if not isinstance(raw, dict):
        raw = {}
    return {key: safe_float(raw.get(key), default) for key, default in defaults.items()}


def fmt_percent_points(raw: object) -> str:
    value_num = safe_float(raw, 0.0)
    rounded = round(value_num)
    return f"{rounded:.0f}%" if abs(value_num - rounded) < 1e-9 else f"{value_num:.1f}%"


def fmt_ratio(raw: object) -> str:
    return f"{safe_float(raw, 0.0):.2f}"


def fmt_scalar(raw: object) -> str:
    value_num = safe_float(raw, 0.0)
    return f"{value_num:.0f}" if float(value_num).is_integer() else f"{value_num:.1f}"


def component_with_weight(component: object, weight: object) -> str:
    base = "—" if component in (None, "—") else score(component)
    return f"{base} · W {fmt_percent_points(weight)}"
