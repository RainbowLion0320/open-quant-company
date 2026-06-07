"""Runtime parameter catalog for candidate strategies."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from core.settings import get_dotted, get_settings, set_dotted


def _param(
    key: str,
    label: str,
    typ: str,
    default: int | float,
    *,
    min_val: int | float | None = None,
    max_val: int | float | None = None,
    description: str = "",
) -> dict[str, Any]:
    item: dict[str, Any] = {"key": key, "label": label, "type": typ, "default": default}
    if min_val is not None:
        item["min"] = min_val
    if max_val is not None:
        item["max"] = max_val
    if description:
        item["description"] = description
    return item


CANDIDATE_PARAM_FIELDS: dict[str, list[dict[str, Any]]] = {
    "trend_following": [
        _param("min_history_days", "最少历史天数", "int", 130, min_val=5, max_val=500),
        _param("short_ma_window", "短均线窗口", "int", 20, min_val=2, max_val=120),
        _param("medium_ma_window", "中均线窗口", "int", 60, min_val=3, max_val=240),
        _param("long_ma_window", "长均线窗口", "int", 120, min_val=5, max_val=500),
        _param("momentum_window", "动量窗口", "int", 60, min_val=2, max_val=240),
        _param("score_weights.trend", "趋势结构权重", "float", 0.40, min_val=0, max_val=1),
        _param("score_weights.above_long_ma", "长均线过滤权重", "float", 0.30, min_val=0, max_val=1),
        _param("score_weights.momentum", "动量排名权重", "float", 0.30, min_val=0, max_val=1),
        _param("trend_score_values.strong", "强趋势分", "float", 100.0, min_val=0, max_val=100),
        _param("trend_score_values.medium", "中趋势分", "float", 75.0, min_val=0, max_val=100),
        _param("trend_score_values.price_above_medium", "价格站上中均线分", "float", 50.0, min_val=0, max_val=100),
        _param("trend_score_values.price_above_long", "价格站上长均线分", "float", 25.0, min_val=0, max_val=100),
    ],
    "donchian_breakout": [
        _param("min_history_days", "最少历史天数", "int", 60, min_val=5, max_val=500),
        _param("breakout_window", "突破通道窗口", "int", 55, min_val=3, max_val=260),
        _param("volume_window", "量能确认窗口", "int", 20, min_val=2, max_val=120),
        _param("volatility_window", "波动率窗口", "int", 20, min_val=2, max_val=120),
        _param("score_weights.breakout_proximity", "突破接近度权重", "float", 0.60, min_val=0, max_val=1),
        _param("score_weights.volume", "量能排名权重", "float", 0.20, min_val=0, max_val=1),
        _param("score_weights.inverse_volatility", "低波排名权重", "float", 0.20, min_val=0, max_val=1),
    ],
    "rps_relative_strength": [
        _param("min_history_days", "最少历史天数", "int", 130, min_val=5, max_val=500),
        _param("short_return_window", "短相对强弱窗口", "int", 42, min_val=2, max_val=240),
        _param("long_return_window", "长相对强弱窗口", "int", 105, min_val=5, max_val=500),
        _param("skip_recent_window", "跳过近期窗口", "int", 21, min_val=0, max_val=120),
        _param("trend_ma_window", "趋势过滤均线窗口", "int", 120, min_val=5, max_val=500),
        _param("score_weights.short_rps", "短 RPS 权重", "float", 0.45, min_val=0, max_val=1),
        _param("score_weights.long_rps", "长 RPS 权重", "float", 0.45, min_val=0, max_val=1),
        _param("score_weights.trend_filter", "趋势过滤权重", "float", 0.10, min_val=0, max_val=1),
    ],
    "sector_rotation": [
        _param("min_history_days", "最少历史天数", "int", 70, min_val=5, max_val=500),
        _param("short_return_window", "行业短周期窗口", "int", 20, min_val=2, max_val=180),
        _param("long_return_window", "行业长周期窗口", "int", 60, min_val=5, max_val=360),
        _param("score_weights.industry_short", "行业短周期权重", "float", 0.60, min_val=0, max_val=1),
        _param("score_weights.industry_long", "行业长周期权重", "float", 0.25, min_val=0, max_val=1),
        _param("score_weights.stock_inside_industry", "行业内个股权重", "float", 0.15, min_val=0, max_val=1),
    ],
    "quality_value": [
        _param("recent_period_count", "财务近期期数", "int", 5, min_val=1, max_val=20),
        _param("score_weights.roe", "ROE 权重", "float", 0.35, min_val=0, max_val=1),
        _param("score_weights.gross_margin", "毛利率权重", "float", 0.25, min_val=0, max_val=1),
        _param("score_weights.inverse_pe", "低 PE 权重", "float", 0.20, min_val=0, max_val=1),
        _param("score_weights.inverse_pb", "低 PB 权重", "float", 0.20, min_val=0, max_val=1),
    ],
    "low_vol_defensive": [
        _param("min_history_days", "最少历史天数", "int", 70, min_val=5, max_val=500),
        _param("volatility_window", "波动率窗口", "int", 60, min_val=2, max_val=260),
        _param("drawdown_window", "回撤控制窗口", "int", 60, min_val=2, max_val=260),
        _param("trend_window", "防御趋势窗口", "int", 20, min_val=2, max_val=180),
        _param("liquidity_window", "流动性窗口", "int", 20, min_val=2, max_val=180),
        _param("trend_score_base", "趋势分基准", "float", 50.0, min_val=0, max_val=100),
        _param("trend_score_scale", "趋势分缩放", "float", 500.0, min_val=0, max_val=2000),
        _param("score_weights.inverse_volatility", "低波排名权重", "float", 0.40, min_val=0, max_val=1),
        _param("score_weights.drawdown_control", "回撤控制权重", "float", 0.30, min_val=0, max_val=1),
        _param("score_weights.trend", "趋势权重", "float", 0.20, min_val=0, max_val=1),
        _param("score_weights.liquidity", "流动性权重", "float", 0.10, min_val=0, max_val=1),
    ],
    "volume_confirmation": [
        _param("min_history_days", "最少历史天数", "int", 25, min_val=5, max_val=260),
        _param("volume_window", "量能窗口", "int", 20, min_val=2, max_val=180),
        _param("momentum_window", "价格动量窗口", "int", 20, min_val=2, max_val=180),
        _param("flow_window", "资金流代理窗口", "int", 20, min_val=2, max_val=180),
        _param("score_weights.volume", "量能权重", "float", 0.45, min_val=0, max_val=1),
        _param("score_weights.momentum", "动量权重", "float", 0.35, min_val=0, max_val=1),
        _param("score_weights.flow", "资金流代理权重", "float", 0.20, min_val=0, max_val=1),
    ],
    "regime_gated": [
        _param("min_active_weight", "最小激活权重", "float", 0.01, min_val=0, max_val=1),
        _param("bear_cash_probability_threshold", "现金防御熊市概率阈值", "float", 0.30, min_val=0, max_val=1),
        _param("cash_score", "现金防御分", "float", 80.0, min_val=0, max_val=100),
        _param("normal_max_buys", "常规最大买入数", "int", 20, min_val=1, max_val=200),
        _param("bear_max_buys", "熊市最大买入数", "int", 10, min_val=1, max_val=200),
        _param("regime_weights.bull.trend_following", "牛市趋势跟随权重", "float", 0.55, min_val=0, max_val=1),
        _param("regime_weights.bull.rps_relative_strength", "牛市 RPS 权重", "float", 0.45, min_val=0, max_val=1),
        _param("regime_weights.sideways.quality_value", "震荡质量价值权重", "float", 0.55, min_val=0, max_val=1),
        _param("regime_weights.sideways.low_vol_defensive", "震荡低波防御权重", "float", 0.45, min_val=0, max_val=1),
        _param("regime_weights.bear.low_vol_defensive", "熊市低波防御权重", "float", 1.0, min_val=0, max_val=1),
    ],
}

CANDIDATE_STRATEGY_NAMES = tuple(CANDIDATE_PARAM_FIELDS.keys())


def _defaults_from_fields(fields: list[dict[str, Any]]) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for item in fields:
        if "default" in item:
            set_dotted(defaults, str(item["key"]), copy.deepcopy(item["default"]))
    return defaults


DEFAULT_CANDIDATE_PARAMS: dict[str, dict[str, Any]] = {
    name: _defaults_from_fields(fields) for name, fields in CANDIDATE_PARAM_FIELDS.items()
}


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def candidate_strategy_params(strategy: str, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return candidate strategy params with canonical defaults merged with settings."""
    defaults = DEFAULT_CANDIDATE_PARAMS.get(strategy, {})
    cfg = config if config is not None else get_settings()
    raw = get_dotted(cfg, f"strategies.{strategy}.params", {}) if isinstance(cfg, Mapping) else {}
    override = raw if isinstance(raw, Mapping) else {}
    return _deep_merge(defaults, override)
