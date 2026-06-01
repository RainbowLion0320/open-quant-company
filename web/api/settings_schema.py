"""Configuration center schema — describes editable parameters for the frontend.

Each section has a list of field descriptors. The frontend uses these to render
type-aware input controls with labels, descriptions, and validation ranges.
"""
from __future__ import annotations

from typing import Any

from core.settings import get_dotted


def _field(key: str, label: str, typ: str = "float", *,
           description: str = "", min_val: Any = None, max_val: Any = None,
           default: Any = None, options: list | None = None) -> dict:
    f: dict[str, Any] = {"key": key, "label": label, "type": typ}
    if description:
        f["description"] = description
    if min_val is not None:
        f["min"] = min_val
    if max_val is not None:
        f["max"] = max_val
    if default is not None:
        f["default"] = default
    if options is not None:
        f["options"] = options
    return f


SETTINGS_SECTIONS: list[dict[str, Any]] = [
    {
        "key": "data.fetcher",
        "label": "数据获取",
        "description": "API 请求节流、重试、缓存参数",
        "fields": [
            _field("min_interval", "请求最小间隔(秒)", "float", min_val=0.5, max_val=30, default=3.0,
                   description="两次 API 请求之间的最小等待时间"),
            _field("jitter_max", "抖动最大值(秒)", "float", min_val=0, max_val=5, default=0.5),
            _field("max_retries", "最大重试次数", "int", min_val=0, max_val=10, default=3),
            _field("base_delay", "退避基础延迟(秒)", "float", min_val=0.5, max_val=30, default=2.0),
            _field("backoff_factor", "退避倍数", "float", min_val=1.0, max_val=10, default=2.0),
            _field("jitter_ratio", "退避抖动比例", "float", min_val=0, max_val=1, default=0.3),
            _field("mem_cache_max", "内存缓存条目上限", "int", min_val=8, max_val=1024, default=64),
            _field("ttl_daily_hours", "日线缓存TTL(小时)", "int", min_val=1, max_val=168, default=24),
            _field("ttl_realtime_hours", "实时缓存TTL(小时)", "int", min_val=0, max_val=24, default=1),
            _field("socket_timeout", "网络超时(秒)", "int", min_val=5, max_val=120, default=30),
        ],
    },
    {
        "key": "cybernetics.score_weights",
        "label": "Regime 评分权重",
        "description": "市场状态检测的四维权重 (总和建议100)",
        "fields": [
            _field("trend", "趋势权重", "float", min_val=0, max_val=100, default=30),
            _field("breadth", "广度权重", "float", min_val=0, max_val=100, default=30),
            _field("risk", "风险权重", "float", min_val=0, max_val=100, default=30),
            _field("volume", "量能权重", "float", min_val=0, max_val=100, default=10),
        ],
    },
    {
        "key": "cybernetics.breadth_weights",
        "label": "广度强度权重",
        "description": "市场广度强度计算公式权重",
        "fields": [
            _field("advance_ratio", "上涨比例权重", "float", min_val=0, max_val=1, default=0.35),
            _field("above_ma20", "MA20上方权重", "float", min_val=0, max_val=1, default=0.30),
            _field("above_ma60", "MA60上方权重", "float", min_val=0, max_val=1, default=0.25),
            _field("above_ma120", "MA120上方权重", "float", min_val=0, max_val=1, default=0.10),
        ],
    },
    {
        "key": "cybernetics.risk_strength_weights",
        "label": "风险强度权重",
        "description": "风险强度中回撤、波动和下跌压力的组合权重",
        "fields": [
            _field("drawdown", "回撤权重", "float", min_val=0, max_val=1, default=0.50),
            _field("volatility", "波动权重", "float", min_val=0, max_val=1, default=0.30),
            _field("pressure", "下跌压力权重", "float", min_val=0, max_val=1, default=0.20),
        ],
    },
    {
        "key": "cybernetics.adaptive.detection",
        "label": "Regime 判定阈值",
        "description": "牛熊阈值、趋势/广度确认、驻留门槛和量能确认阈值",
        "fields": [
            _field("regime_bull_threshold", "牛市评分阈值", "float", min_val=0, max_val=100, default=60),
            _field("regime_bear_threshold", "熊市评分阈值", "float", min_val=0, max_val=100, default=40),
            _field("regime_trend_confirm", "牛市趋势确认", "float", min_val=0, max_val=1, default=0.55),
            _field("breadth_bull_threshold", "牛市广度确认", "float", min_val=0, max_val=1, default=0.55),
            _field("regime_bear_trend_breakdown", "熊市趋势击穿", "float", min_val=0, max_val=1, default=0.40),
            _field("breadth_bear_threshold", "熊市广度击穿", "float", min_val=0, max_val=1, default=0.40),
            _field("regime_min_dwell", "状态切换最小驻留", "int", min_val=1, max_val=20, default=3),
            _field("volume_expansion", "放量阈值", "float", min_val=1.0, max_val=3.0, default=1.20),
            _field("volume_contraction", "缩量阈值", "float", min_val=0.1, max_val=1.0, default=0.80),
        ],
    },
    {
        "key": "cybernetics",
        "label": "Regime 检测参数",
        "description": "HMM 置信度、缓存、最小数据量等",
        "fields": [
            _field("hmm_confidence_override", "HMM置信度覆盖阈值", "float", min_val=0.5, max_val=1.0, default=0.80,
                   description="HMM 置信度超过此值时直接信任 HMM 结果"),
            _field("min_bars_trend", "趋势最小数据量", "int", min_val=20, max_val=252, default=60),
            _field("min_bars_risk", "风险最小数据量", "int", min_val=10, max_val=120, default=30),
        ],
    },
    {
        "key": "signals.multifactor.momentum",
        "label": "动量因子参数",
        "description": "多因子策略动量评分参数",
        "fields": [
            _field("weight_3m", "3月动量权重", "float", min_val=0, max_val=1, default=0.35),
            _field("weight_6m", "6月动量权重", "float", min_val=0, max_val=1, default=0.65),
            _field("strong_threshold", "强势阈值", "float", min_val=0.05, max_val=0.5, default=0.15),
            _field("strong_score", "强势评分", "float", min_val=0, max_val=100, default=40),
            _field("multiplier_strong", "强势乘数", "float", min_val=50, max_val=1000, default=400),
            _field("multiplier_normal", "正常乘数", "float", min_val=50, max_val=1000, default=200),
            _field("weak_floor", "弱势底线", "float", min_val=0, max_val=50, default=20),
        ],
    },
    {
        "key": "signals.multifactor.trend_penalty",
        "label": "趋势惩罚参数",
        "description": "下跌趋势对动量评分的惩罚",
        "fields": [
            _field("threshold", "惩罚阈值", "float", min_val=-0.5, max_val=0, default=-0.05,
                   description="趋势强度低于此值时触发惩罚"),
            _field("multiplier", "惩罚乘数", "float", min_val=0.1, max_val=1.0, default=0.55),
        ],
    },
    {
        "key": "signals.multifactor.roe_trend",
        "label": "ROE 趋势判定",
        "description": "ROE 趋势分类参数",
        "fields": [
            _field("up_threshold", "上升阈值", "float", min_val=1.0, max_val=1.5, default=1.05,
                   description="最新ROE > 最早ROE * 此值 → 上升趋势"),
            _field("down_threshold", "下降阈值", "float", min_val=0.5, max_val=1.0, default=0.95),
            _field("min_years", "最小年数", "int", min_val=2, max_val=10, default=3),
        ],
    },
    {
        "key": "signals.multifactor",
        "label": "多因子权重",
        "description": "五维复合评分权重 (总和建议1.0)",
        "fields": [
            _field("weights.quality", "质量权重", "float", min_val=0, max_val=1, default=0.35),
            _field("weights.valuation", "估值权重", "float", min_val=0, max_val=1, default=0.25),
            _field("weights.technical", "技术权重", "float", min_val=0, max_val=1, default=0.15),
            _field("weights.market", "市场权重", "float", min_val=0, max_val=1, default=0.10),
            _field("weights.industry_momentum", "行业动量权重", "float", min_val=0, max_val=1, default=0.15),
        ],
    },
    {
        "key": "buffett.margin_of_safety",
        "label": "巴菲特安全边际",
        "description": "DCF 折现、永续增长和安全边际参数",
        "fields": [
            _field("dcf_discount_rate", "DCF折现率", "float", min_val=0.03, max_val=0.20, default=0.08),
            _field("growth_rate_terminal", "永续增长率", "float", min_val=0.01, max_val=0.10, default=0.03),
            _field("safety_margin_pct", "安全边际要求", "float", min_val=0.1, max_val=0.6, default=0.30),
        ],
    },
    {
        "key": "buffett.valuation",
        "label": "巴菲特估值扩展",
        "description": "DCF 高增长期和终值估算参数",
        "fields": [
            _field("growth_period", "DCF增长期(年)", "int", min_val=3, max_val=10, default=5),
            _field("terminal_pe", "终值PE倍数", "float", min_val=5, max_val=50, default=20),
        ],
    },
    {
        "key": "trading.exchange.stock",
        "label": "A股交易费率",
        "description": "股票交易的印花税、佣金、过户费等",
        "fields": [
            _field("stamp_tax", "印花税", "float", min_val=0, max_val=0.01, default=0.0005,
                   description="卖出单向征收"),
            _field("commission", "佣金率", "float", min_val=0, max_val=0.01, default=0.00025,
                   description="双向征收"),
            _field("transfer_fee", "过户费率", "float", min_val=0, max_val=0.001, default=0.00001),
            _field("min_commission", "最低佣金(元)", "float", min_val=0, max_val=50, default=5.0),
            _field("lot_size", "每手股数", "int", min_val=1, max_val=1000, default=100),
        ],
    },
    {
        "key": "risk_control",
        "label": "风控限制",
        "description": "仓位、敞口、单笔、回撤限制",
        "fields": [
            _field("max_single_position.max_pct", "单票仓位上限", "float", min_val=0.05, max_val=1.0, default=0.25),
            _field("max_total_exposure.max_pct", "总敞口上限", "float", min_val=0.1, max_val=1.0, default=0.80),
            _field("max_orders_per_day.max_count", "每日订单上限", "int", min_val=1, max_val=200, default=20),
            _field("max_drawdown_circuit_breaker.max_drawdown_pct", "回撤熔断阈值", "float",
                   min_val=-0.50, max_val=-0.05, default=-0.15),
            _field("max_single_order_amount.max_amount", "单笔金额上限", "float",
                   min_val=10000, max_val=5000000, default=500000),
        ],
    },
    {
        "key": "backtest",
        "label": "回测参数",
        "description": "回测日期范围、最小数据量、再平衡参数",
        "fields": [
            _field("start_date", "起始日期", "string", default="2015-01-01"),
            _field("end_date", "结束日期", "string", default="2026-05-10"),
            _field("min_bars", "最小数据条数", "int", min_val=50, max_val=500, default=200),
            _field("min_history", "评分最小历史(天)", "int", min_val=20, max_val=252, default=63),
            _field("alpha_min_score", "Alpha最低评分", "float", min_val=0, max_val=100, default=30),
            _field("rebalance.drift_threshold", "漂移再平衡阈值", "float", min_val=0.1, max_val=1.0, default=0.75),
            _field("rebalance.overlap_threshold", "重叠度阈值", "float", min_val=0.1, max_val=1.0, default=0.50),
            _field("rebalance.max_idle_days", "最大空闲天数", "int", min_val=7, max_val=365, default=28),
        ],
    },
    {
        "key": "data_cleaning",
        "label": "数据清洗",
        "description": "OHLCV 清洗规则参数",
        "fields": [
            _field("outlier_detection.sigma", "异常值标准差", "float", min_val=1, max_val=10, default=5),
            _field("outlier_detection.max_daily_change_pct", "最大日涨跌幅", "float",
                   min_val=0.05, max_val=0.50, default=0.20),
            _field("suspended_detection.max_flat_days", "停牌判定天数", "int", min_val=5, max_val=120, default=60),
            _field("missing_value.max_forward_fill", "前向填充天数", "int", min_val=1, max_val=20, default=5),
            _field("winsorize.lower_pct", "缩尾下限", "float", min_val=0.001, max_val=0.10, default=0.01),
            _field("winsorize.upper_pct", "缩尾上限", "float", min_val=0.90, max_val=0.999, default=0.99),
        ],
    },
]


def get_settings_schema() -> dict:
    """Return the full schema for the config center."""
    return {
        "sections": SETTINGS_SECTIONS,
        "total_sections": len(SETTINGS_SECTIONS),
        "total_fields": sum(len(s["fields"]) for s in SETTINGS_SECTIONS),
    }


def validate_settings_section(section: str, data: dict[str, Any]) -> list[str]:
    """Validate one config section payload against the editable settings schema."""
    matching_schemas = [
        schema
        for schema in SETTINGS_SECTIONS
        if schema["key"] == section or schema["key"].startswith(section + ".")
    ]
    if not matching_schemas:
        return []

    errors: list[str] = []
    for schema in matching_schemas:
        for field in schema["fields"]:
            key = field["key"]
            val = get_dotted(data, key)
            if val is None:
                continue

            ftype = field.get("type", "float")
            fmin = field.get("min")
            fmax = field.get("max")

            if ftype == "int" and not isinstance(val, int):
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    errors.append(f"{key}: expected int, got {type(val).__name__}")
                    continue
            elif ftype == "float" and not isinstance(val, (int, float)):
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    errors.append(f"{key}: expected float, got {type(val).__name__}")
                    continue

            if fmin is not None and val < fmin:
                errors.append(f"{key}: {val} < min ({fmin})")
            if fmax is not None and val > fmax:
                errors.append(f"{key}: {val} > max ({fmax})")

    return errors
