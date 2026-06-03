"""Index trend and risk strength helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional
import math

from cybernetics.config import _load_config
from cybernetics.types import MarketBreadth
from cybernetics.observations.sources import _clamp, _frame_close_volume, _regime_indexes

def _index_trend_strength(df) -> Optional[float]:
    data = _frame_close_volume(df)
    if len(data) < 60:
        return None

    close = data["close"]
    current = float(close.iloc[-1])
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean())
    ma120 = float(close.tail(120).mean()) if len(close) >= 120 else ma60

    checks = [
        current > ma20,
        current > ma60,
        ma20 > ma60,
        current > ma120,
    ]
    if len(close) >= 80:
        prev_ma20 = float(close.iloc[-40:-20].mean())
        checks.append(ma20 > prev_ma20)

    return sum(1 for ok in checks if ok) / len(checks)

def _compute_multi_index_trend(index_frames: Dict[str, Any]) -> tuple[float, Dict[str, float]]:
    weighted = 0.0
    total_weight = 0.0
    detail: Dict[str, float] = {}

    for symbol, _label, weight in _regime_indexes():
        strength = _index_trend_strength(index_frames.get(symbol))
        if strength is None:
            continue
        detail[symbol] = round(strength, 4)
        weighted += strength * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.5, detail
    return weighted / total_weight, detail

def _index_risk_metrics(df) -> Optional[Dict[str, float]]:
    data = _frame_close_volume(df)
    if len(data) < 30:
        return None

    close = data["close"]
    returns = close.pct_change().dropna()
    if len(returns) < 10:
        realized_vol = 0.0
    else:
        realized_vol = float(returns.tail(20).std() * math.sqrt(252))
        if not math.isfinite(realized_vol):
            realized_vol = 0.0

    window = close.tail(60)
    peak = float(window.max())
    current = float(close.iloc[-1])
    drawdown = (current / peak - 1.0) if peak > 0 else 0.0

    vol_score = 1.0 - _clamp((realized_vol - 0.12) / 0.28)
    drawdown_score = 1.0 - _clamp(abs(min(drawdown, 0.0)) / 0.15)
    return {
        "realized_vol_20d": realized_vol,
        "drawdown_60d": drawdown,
        "vol_score": vol_score,
        "drawdown_score": drawdown_score,
    }

def _compute_risk_strength(
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
) -> tuple[float, Dict[str, float]]:
    try:
        risk_weights = (_load_config().get("risk_strength_weights", {}) or {})
    except Exception:
        risk_weights = {}
    drawdown_weight = float(risk_weights.get("drawdown", 0.50))
    volatility_weight = float(risk_weights.get("volatility", 0.30))
    pressure_weight = float(risk_weights.get("pressure", 0.20))
    total_component_weight = drawdown_weight + volatility_weight + pressure_weight
    if total_component_weight <= 0:
        drawdown_weight, volatility_weight, pressure_weight = 0.50, 0.30, 0.20
        total_component_weight = 1.0
    drawdown_weight /= total_component_weight
    volatility_weight /= total_component_weight
    pressure_weight /= total_component_weight

    weighted_vol_score = 0.0
    weighted_drawdown_score = 0.0
    weighted_realized_vol = 0.0
    weighted_drawdown = 0.0
    total_weight = 0.0
    worst_drawdown = 0.0
    index_detail: Dict[str, float] = {}

    for symbol, _label, weight in _regime_indexes():
        metrics = _index_risk_metrics(index_frames.get(symbol))
        if not metrics:
            continue
        weighted_vol_score += metrics["vol_score"] * weight
        weighted_drawdown_score += metrics["drawdown_score"] * weight
        weighted_realized_vol += metrics["realized_vol_20d"] * weight
        weighted_drawdown += metrics["drawdown_60d"] * weight
        worst_drawdown = min(worst_drawdown, metrics["drawdown_60d"])
        index_detail[f"risk_vol_{symbol}"] = round(metrics["realized_vol_20d"], 4)
        index_detail[f"risk_drawdown_{symbol}"] = round(metrics["drawdown_60d"], 4)
        total_weight += weight

    if total_weight <= 0:
        vol_health = 0.5
        drawdown_health = 0.5
        weighted_realized_vol = 0.0
        weighted_drawdown = 0.0
    else:
        vol_health = weighted_vol_score / total_weight
        drawdown_health = weighted_drawdown_score / total_weight
        weighted_realized_vol = weighted_realized_vol / total_weight
        weighted_drawdown = weighted_drawdown / total_weight

    traded = breadth.up_count + breadth.down_count + breadth.unchanged_count
    down_ratio = (breadth.down_count / traded) if traded else 0.5
    pressure_raw = (
        0.50 * down_ratio
        + 0.30 * (1.0 - breadth.above_ma20)
        + 0.20 * (1.0 - breadth.above_ma60)
    )
    pressure_health = 1.0 - _clamp((pressure_raw - 0.40) / 0.35)

    strength = (
        drawdown_weight * drawdown_health
        + volatility_weight * vol_health
        + pressure_weight * pressure_health
    )
    return strength, {
        "risk_drawdown_raw": round(drawdown_health, 4),
        "risk_volatility_raw": round(vol_health, 4),
        "risk_pressure_raw": round(pressure_health, 4),
        "risk_drawdown_weight": round(drawdown_weight, 4),
        "risk_volatility_weight": round(volatility_weight, 4),
        "risk_pressure_weight": round(pressure_weight, 4),
        "market_down_pressure": round(pressure_raw, 4),
        "market_down_ratio": round(down_ratio, 4),
        "realized_vol_20d": round(weighted_realized_vol, 4),
        "drawdown_60d": round(weighted_drawdown, 4),
        "worst_drawdown_60d": round(worst_drawdown, 4),
        **index_detail,
    }
