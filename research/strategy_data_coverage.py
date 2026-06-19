"""Strategy data coverage matrix.

This module answers a narrow governance question: which data families each
strategy declares and whether that is enough for the strategy's own type.
It is not a repository-wide lineage scanner.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from research.strategy_catalog import StrategyCatalogItem, catalog_items
from research.strategy_evaluation import load_evidence_artifact


FAMILIES: list[dict[str, str]] = [
    {"key": "price", "label_zh": "价格", "label_en": "Price"},
    {"key": "volume", "label_zh": "成交量", "label_en": "Volume"},
    {"key": "financial", "label_zh": "财务", "label_en": "Financial"},
    {"key": "valuation", "label_zh": "估值", "label_en": "Valuation"},
    {"key": "sector", "label_zh": "行业", "label_en": "Sector"},
    {"key": "features", "label_zh": "特征", "label_en": "Features"},
    {"key": "regime", "label_zh": "市场状态", "label_en": "Regime"},
    {"key": "portfolio", "label_zh": "组合", "label_en": "Portfolio"},
    {"key": "moneyflow", "label_zh": "资金流", "label_en": "Money Flow"},
    {"key": "macro", "label_zh": "宏观", "label_en": "Macro"},
    {"key": "sentiment", "label_zh": "情绪", "label_en": "Sentiment"},
    {"key": "risk_free", "label_zh": "无风险利率", "label_en": "Risk-Free Rate"},
]
FAMILY_KEYS = [item["key"] for item in FAMILIES]

DIMENSION_FAMILY_MAP: dict[str, tuple[str, ...]] = {
    "stock_daily": ("price", "volume"),
    "raw_price": ("price",),
    "adjusted_price": ("price",),
    "ohlcv_daily": ("price", "volume"),
    "features": ("features",),
    "features_all": ("features",),
    "financials": ("financial",),
    "financial_summary": ("financial",),
    "fina_indicator": ("financial",),
    "income_statement": ("financial",),
    "balance_sheet": ("financial",),
    "cashflow_statement": ("financial",),
    "valuation_daily": ("valuation",),
    "sector": ("sector",),
    "sector_membership": ("sector",),
    "sector_signal_snapshot": ("sector",),
    "sector_performance_snapshot": ("sector",),
    "market_regime": ("regime",),
    "regime": ("regime",),
    "portfolio": ("portfolio",),
    "holdings": ("portfolio",),
    "moneyflow": ("moneyflow",),
    "moneyflow_tushare_daily": ("moneyflow",),
    "moneyflow_monthly": ("moneyflow",),
    "stock_moneyflow_daily": ("moneyflow",),
    "stock_research_report": ("sentiment",),
    "research_report": ("sentiment",),
    "news": ("sentiment",),
    "macro": ("macro",),
    "macro_gdp": ("macro",),
    "macro_cpi": ("macro",),
    "macro_pmi": ("macro",),
    "risk_free_curve": ("risk_free",),
    "bond_treasury_yields": ("risk_free",),
}

TYPE_EXPECTATIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "selection": {
        "required": ("price",),
        "optional": ("volume", "financial", "valuation", "sector", "moneyflow", "sentiment", "macro"),
    },
    "timing": {
        "required": ("price", "volume"),
        "optional": ("regime", "moneyflow", "sector", "macro"),
    },
    "sector_rotation": {
        "required": ("price", "sector"),
        "optional": ("volume", "regime", "moneyflow", "macro"),
    },
    "portfolio": {
        "required": ("price", "regime", "portfolio"),
        "optional": ("macro", "risk_free", "moneyflow"),
    },
    "risk_overlay": {
        "required": ("price", "regime", "portfolio"),
        "optional": ("macro", "risk_free"),
    },
}

LAYER_EXPECTATION_OVERRIDES: dict[str, dict[str, tuple[str, ...]]] = {
    "quality_filter": {
        "required": ("price", "financial", "valuation"),
        "optional": ("sector", "macro"),
    },
    "primary_alpha": {
        "required": ("price", "financial", "valuation", "sector"),
        "optional": ("volume", "moneyflow", "sentiment", "macro"),
    },
    "auxiliary_alpha": {
        "required": ("price", "features", "sector"),
        "optional": ("volume", "financial", "valuation", "regime", "macro"),
    },
    "risk_overlay": {
        "required": ("price", "regime", "portfolio"),
        "optional": ("macro", "risk_free"),
    },
}


def _sorted_families(values: Iterable[str]) -> list[str]:
    unique = set(values)
    return [key for key in FAMILY_KEYS if key in unique]


def families_for_dimensions(dimensions: Iterable[str]) -> list[str]:
    families: set[str] = set()
    for raw in dimensions:
        item = str(raw).strip()
        if not item:
            continue
        if item in FAMILY_KEYS:
            families.add(item)
            continue
        families.update(DIMENSION_FAMILY_MAP.get(item, ()))
    return _sorted_families(families)


def _expectations(item: StrategyCatalogItem) -> dict[str, list[str]]:
    base = TYPE_EXPECTATIONS.get(item.strategy_type, TYPE_EXPECTATIONS["selection"])
    required = set(base.get("required", ()))
    optional = set(base.get("optional", ()))
    override = LAYER_EXPECTATION_OVERRIDES.get(item.layer)
    if override:
        required.update(override.get("required", ()))
        optional.update(override.get("optional", ()))
    optional.difference_update(required)
    return {
        "required": _sorted_families(required),
        "optional": _sorted_families(optional),
        "not_applicable": [key for key in FAMILY_KEYS if key not in required and key not in optional],
    }


def _observed_dimensions(evidence: dict[str, Any]) -> list[str]:
    artifact = evidence.get("artifact") if isinstance(evidence, dict) else {}
    if not isinstance(artifact, dict):
        return []
    candidates = [
        artifact.get("data_coverage", {}),
        artifact.get("backtest_evidence", {}),
        artifact.get("data_readiness", {}),
    ]
    observed: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in ("observed_dimensions", "declared_dimensions", "dimensions"):
            value = candidate.get(key)
            if isinstance(value, list):
                observed.extend(str(item) for item in value)
    return sorted(set(item for item in observed if item))


def _row(
    item: StrategyCatalogItem,
    *,
    evidence_loader: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    declared_dimensions = sorted(set(str(dim) for dim in item.data_requirements if str(dim).strip()))
    declared_families = set(families_for_dimensions(declared_dimensions))
    evidence = evidence_loader(item.name)
    observed_dimensions = _observed_dimensions(evidence)
    observed_families = set(families_for_dimensions(observed_dimensions))
    expectations = _expectations(item)
    required = set(expectations["required"])
    optional = set(expectations["optional"])
    missing_required = _sorted_families(required - declared_families)
    optional_missing = _sorted_families(optional - declared_families)
    unused_declared = [
        family
        for family in _sorted_families(declared_families)
        if family not in required and family not in optional
    ]
    cells: dict[str, dict[str, Any]] = {}
    for family in FAMILY_KEYS:
        declared = family in declared_families
        observed = family in observed_families
        if declared:
            status = "declared"
        elif observed:
            status = "observed"
        elif family in required:
            status = "required_missing"
        elif family in optional:
            status = "optional_missing"
        else:
            status = "not_applicable"
        cells[family] = {
            "status": status,
            "declared": declared,
            "observed": observed,
            "expectation": "required" if family in required else "optional" if family in optional else "not_applicable",
        }
    required_score = 1.0 if not required else (len(required - set(missing_required)) / len(required))
    return {
        "strategy": item.name,
        "label": item.label,
        "strategy_type": item.strategy_type,
        "layer": item.layer,
        "lifecycle": item.lifecycle,
        "declared_dimensions": declared_dimensions,
        "declared_families": _sorted_families(declared_families),
        "observed_dimensions": observed_dimensions,
        "observed_families": _sorted_families(observed_families),
        "observed_status": "measured" if observed_dimensions else "missing_evidence",
        "required_families": expectations["required"],
        "optional_families": expectations["optional"],
        "not_applicable_families": expectations["not_applicable"],
        "missing_required_families": missing_required,
        "optional_missing_families": optional_missing,
        "unused_declared_families": unused_declared,
        "coverage_score": round(required_score, 4),
        "cells": cells,
    }


def build_strategy_data_coverage(
    *,
    items: Iterable[StrategyCatalogItem] | None = None,
    evidence_loader: Callable[[str], dict[str, Any]] = load_evidence_artifact,
) -> dict[str, Any]:
    rows = [_row(item, evidence_loader=evidence_loader) for item in (list(items) if items is not None else catalog_items())]
    required_gap_count = sum(len(row["missing_required_families"]) for row in rows)
    optional_gap_count = sum(len(row["optional_missing_families"]) for row in rows)
    return {
        "status": "ok",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "recommended_command": "astroq strategy data-coverage --json",
        "families": FAMILIES,
        "expectations": {
            "by_type": TYPE_EXPECTATIONS,
            "by_layer": LAYER_EXPECTATION_OVERRIDES,
        },
        "summary": {
            "strategy_count": len(rows),
            "family_count": len(FAMILIES),
            "required_gap_count": required_gap_count,
            "optional_gap_count": optional_gap_count,
            "missing_observed_count": sum(1 for row in rows if row["observed_status"] == "missing_evidence"),
        },
        "rows": sorted(rows, key=lambda row: (row["lifecycle"] != "production", row["layer"], row["strategy"])),
    }


def write_strategy_data_coverage_payload(payload: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path]:
    from data.storage.datahub import get_datahub

    data = payload or build_strategy_data_coverage()
    path = get_datahub().artifact_path("strategy", "data_coverage_latest.json")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return data, path
