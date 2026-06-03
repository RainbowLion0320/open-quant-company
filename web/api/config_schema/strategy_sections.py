"""Dynamic strategy schema sections derived from config/settings.yaml."""

from __future__ import annotations

from typing import Any

from data.registry import ALLOWED_STATUSES
from web.api.config_schema.fields import field


def _strategy_label(registry: dict[str, Any], name: str) -> str:
    raw = registry.get(name) if isinstance(registry, dict) else None
    if isinstance(raw, dict):
        return str(raw.get("label") or name)
    return name


def _status_options() -> list[dict[str, str]]:
    return [{"label": status, "value": status} for status in ALLOWED_STATUSES]


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
                        field("max_buys", "最大买入数", "int", min_val=1, max_val=500, default=raw.get("max_buys", 20)),
                    ],
                }
            )

    return sections
