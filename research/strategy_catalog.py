"""Strategy catalog contract.

The catalog describes what a strategy is, which data it consumes, and how its
signals should be interpreted. It is intentionally separate from strategy
execution so candidate research can expand without leaking into production.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data.registry import get_enabled_strategies


@dataclass(frozen=True)
class StrategyCatalogItem:
    name: str
    label: str
    strategy_type: str
    layer: str
    lifecycle: str
    data_requirements: list[str]
    parameters: dict[str, Any] = field(default_factory=dict)
    output_contract: str = "StrategySignalRows"
    research_sources: list[str] = field(default_factory=list)


DEFAULT_TYPES: dict[str, tuple[str, str, list[str]]] = {
    "buffett": (
        "selection",
        "quality_filter",
        ["financials", "valuation_daily", "stock_daily"],
    ),
    "multifactor": (
        "selection",
        "primary_alpha",
        ["financials", "valuation_daily", "stock_daily", "sector"],
    ),
    "ml_lgbm": (
        "selection",
        "auxiliary_alpha",
        ["features", "stock_daily", "sector", "market_regime"],
    ),
    "cybernetic": (
        "risk_overlay",
        "risk_overlay",
        ["market_regime", "stock_daily", "portfolio"],
    ),
}


def _list_value(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list) and value:
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return list(fallback)


def _text_value(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def catalog_items() -> list[StrategyCatalogItem]:
    items: list[StrategyCatalogItem] = []
    for raw in get_enabled_strategies():
        strategy_type, layer, requirements = DEFAULT_TYPES.get(
            raw["name"],
            (
                raw.get("strategy_type", "selection"),
                raw.get("layer", "candidate_alpha"),
                raw.get("data_requirements", ["stock_daily"]),
            ),
        )
        items.append(
            StrategyCatalogItem(
                name=raw["name"],
                label=raw.get("label", raw["name"]),
                strategy_type=_text_value(raw.get("strategy_type"), strategy_type),
                layer=_text_value(raw.get("layer"), layer),
                lifecycle=raw.get("status", "candidate"),
                data_requirements=_list_value(raw.get("data_requirements"), requirements),
                parameters=dict(raw.get("parameters", {})),
                output_contract=_text_value(raw.get("output_contract"), "StrategySignalRows"),
                research_sources=_list_value(raw.get("research_sources"), []),
            )
        )
    return sorted(items, key=lambda item: (item.lifecycle != "production", item.layer, item.name))


def catalog_by_name() -> dict[str, StrategyCatalogItem]:
    return {item.name: item for item in catalog_items()}
