from __future__ import annotations

from typing import Any


DESKS: list[dict[str, Any]] = [
    {
        "desk_id": "data",
        "display_name": "Data Desk",
        "mandate": "Source capability, permission, local coverage, freshness, and repair proposals.",
        "allowed_tools": [
            "astroq.data.status",
            "astroq.data.sources",
            "astroq.data.sources.diff_registry",
            "astroq.data.repair.dry_run",
        ],
        "forbidden_actions": ["live_order", "code_change"],
        "handoff_targets": ["research", "risk", "reporting"],
        "status": "available",
    },
    {
        "desk_id": "research",
        "display_name": "Research Desk",
        "mandate": "Strategy evidence, backtests, OOS, IC/ICIR, and promotion proposals.",
        "allowed_tools": [
            "astroq.strategy.catalog",
            "astroq.strategy.compete",
            "astroq.backtest.run.dry_run",
        ],
        "forbidden_actions": ["live_order", "code_change"],
        "handoff_targets": ["data", "risk", "reporting"],
        "status": "available",
    },
    {
        "desk_id": "risk",
        "display_name": "Risk Desk",
        "mandate": "Lifecycle, exposure, data readiness, and execution risk gates.",
        "allowed_tools": ["astroq.lifecycle.check", "astroq.execution.dry_run"],
        "forbidden_actions": ["code_change"],
        "handoff_targets": ["data", "research", "execution", "reporting"],
        "status": "available",
    },
    {
        "desk_id": "execution",
        "display_name": "Execution Desk",
        "mandate": "Paper orders, broker readiness, live proposals, reconciliation, and kill switch state.",
        "allowed_tools": ["astroq.execution.dry_run"],
        "forbidden_actions": ["code_change"],
        "handoff_targets": ["risk", "reporting"],
        "status": "available",
    },
    {
        "desk_id": "engineering",
        "display_name": "Engineering Desk",
        "mandate": "CodeGraph, AST, test design diagnostics, bug triage, and work orders.",
        "allowed_tools": ["astroq.architecture.ast", "astroq.test.design", "astroq.docs.check"],
        "forbidden_actions": ["write_data", "paper_order", "live_order"],
        "handoff_targets": ["data", "research", "risk", "reporting"],
        "status": "available",
    },
    {
        "desk_id": "reporting",
        "display_name": "Reporting Desk",
        "mandate": "Daily CEO brief, weekly review, audit packs, and evidence-cited summaries.",
        "allowed_tools": [
            "astroq.lifecycle.check",
            "astroq.data.status",
            "astroq.strategy.catalog",
        ],
        "forbidden_actions": ["write_config", "write_data", "paper_order", "live_order", "code_change"],
        "handoff_targets": ["data", "research", "risk", "execution", "engineering"],
        "status": "available",
    },
]


def list_desks() -> list[dict[str, Any]]:
    return [dict(desk) for desk in DESKS]
