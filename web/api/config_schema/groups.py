"""Config center top-level groups."""

from __future__ import annotations

from typing import Any


SETTINGS_GROUPS: list[dict[str, Any]] = [
    {
        "key": "strategy_management",
        "label": "策略管理",
        "description": "生产策略、候选策略、选股门槛、策略权重和模型运行参数",
        "order": 10,
    },
    {
        "key": "market_regime",
        "label": "市场状态",
        "description": "Regime 评分、广度、风险强度、HMM 和切换阈值",
        "order": 20,
    },
    {
        "key": "execution_risk",
        "label": "执行与风控",
        "description": "交易费率、PaperBroker、仓位敞口和回撤约束",
        "order": 30,
    },
    {
        "key": "data_ops",
        "label": "数据与清洗",
        "description": "数据获取、缓存、重试、OHLCV 清洗和异常值规则",
        "order": 40,
    },
    {
        "key": "research_backtest",
        "label": "研究回测",
        "description": "回测窗口、最小样本、评分门槛和再平衡参数",
        "order": 50,
    },
    {
        "key": "ai_services",
        "label": "AI 服务",
        "description": "LLM 成本、模型定价和汇率估算参数",
        "order": 60,
    },
]

GROUP_BY_KEY = {group["key"]: group for group in SETTINGS_GROUPS}
