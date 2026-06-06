"""Dynamic strategy schema sections derived from config/settings.yaml."""

from __future__ import annotations

from typing import Any

from data.strategy.catalog import ALLOWED_STATUSES
from signals.candidates.params import CANDIDATE_PARAM_FIELDS
from web.api.config_schema.fields import field


def _strategy_label(registry: dict[str, Any], name: str) -> str:
    raw = registry.get(name) if isinstance(registry, dict) else None
    if isinstance(raw, dict):
        return str(raw.get("label") or name)
    return name


def _status_options() -> list[dict[str, str]]:
    return [{"label": status, "value": status} for status in ALLOWED_STATUSES]


def _candidate_param_field(raw: dict[str, Any]) -> dict[str, Any]:
    return field(
        str(raw["key"]),
        str(raw["label"]),
        str(raw.get("type", "float")),
        description=str(raw.get("description", "")),
        min_val=raw.get("min"),
        max_val=raw.get("max"),
        default=raw.get("default"),
    )


def build_strategy_sections(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Build editable sections for registered strategies and per-strategy gates."""
    registry = config.get("strategies", {}) if isinstance(config, dict) else {}
    selection = config.get("signal_selection", {}) if isinstance(config, dict) else {}
    selection_by_strategy = selection.get("strategies", {}) if isinstance(selection, dict) else {}
    sections: list[dict[str, Any]] = []

    if isinstance(registry, dict):
        for index, (name, raw) in enumerate(registry.items()):
            raw = raw if isinstance(raw, dict) else {}
            sections.append(
                {
                    "key": f"strategies.{name}",
                    "label": f"{raw.get('label') or name} · 生命周期",
                    "description": "策略注册、启用状态和运行生命周期；runner/config_key 由代码审查维护，不在配置中心编辑。",
                    "group": "strategy_management",
                    "subgroup": "strategy_registry",
                    "subgroup_label": "策略注册与生命周期",
                    "strategy_name": name,
                    "strategy_label": raw.get("label") or name,
                    "order": 1000 + index,
                    "fields": [
                        field("enabled", "启用策略", "bool", default=True),
                        field("status", "生命周期", "select", default=raw.get("status", "candidate"), options=_status_options()),
                        field("label", "显示名称", "string", default=raw.get("label", name)),
                        field("color", "展示颜色", "string", default=raw.get("color", "#7170ff")),
                    ],
                }
            )

    if isinstance(registry, dict):
        for index, (name, raw) in enumerate(registry.items()):
            if name not in CANDIDATE_PARAM_FIELDS:
                continue
            raw = raw if isinstance(raw, dict) else {}
            sections.append(
                {
                    "key": f"strategies.{name}.params",
                    "label": f"{raw.get('label') or name} · 核心参数",
                    "description": "该候选策略的研究窗口、评分权重、过滤阈值和组合规则；用于研究扫描与回测，不直接放行生产信号。",
                    "group": "strategy_management",
                    "subgroup": "strategy_params",
                    "subgroup_label": "策略核心参数",
                    "strategy_name": name,
                    "strategy_label": raw.get("label") or name,
                    "order": 1500 + index,
                    "fields": [_candidate_param_field(item) for item in CANDIDATE_PARAM_FIELDS[name]],
                }
            )

    if isinstance(selection_by_strategy, dict):
        for index, (name, raw) in enumerate(selection_by_strategy.items()):
            if not isinstance(raw, dict):
                continue
            label = _strategy_label(registry, name)
            sections.append(
                {
                    "key": f"signal_selection.strategies.{name}",
                    "label": f"{label} · 选股门槛",
                    "description": "该策略从排序结果进入 buy list 的最低分和最大买入数量。",
                    "group": "strategy_management",
                    "subgroup": "strategy_selection",
                    "subgroup_label": "策略级选股门槛",
                    "strategy_name": name,
                    "strategy_label": label,
                    "order": 2000 + index,
                    "fields": [
                        field("min_score", "最低买入分", "float", min_val=0, max_val=100, default=raw.get("min_score", 55)),
                        field("top_pct", "Top 比例", "float", min_val=0.001, max_val=1, default=raw.get("top_pct", selection.get("top_pct", 0.05))),
                        field("min_buys", "最小买入数", "int", min_val=0, max_val=500, default=raw.get("min_buys", selection.get("min_buys", 5))),
                        field("max_buys", "最大买入数", "int", min_val=1, max_val=500, default=raw.get("max_buys", 20)),
                    ],
                }
            )

    return sections
