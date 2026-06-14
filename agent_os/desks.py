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
            "astroq.data.repair",
            "astroq.data.repair.dry_run",
        ],
        "forbidden_actions": ["live_order", "code_change"],
        "evidence_required": ["data_status", "source_capability", "coverage"],
        "handoff_targets": ["research", "risk", "reporting"],
        "default_policy": "approval_required_for_writes",
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
        "evidence_required": ["strategy_evidence", "backtest_evidence", "alpha_evidence"],
        "handoff_targets": ["data", "risk", "reporting"],
        "default_policy": "approval_required_for_official_backtests",
        "status": "available",
    },
    {
        "desk_id": "risk",
        "display_name": "Risk Desk",
        "mandate": "Lifecycle, exposure, data readiness, and execution risk gates.",
        "allowed_tools": ["astroq.lifecycle.check", "astroq.execution.dry_run"],
        "forbidden_actions": ["code_change"],
        "evidence_required": ["lifecycle_readiness", "risk_gate", "execution_readiness"],
        "handoff_targets": ["data", "research", "execution", "reporting"],
        "default_policy": "approval_required_for_gate_override",
        "status": "available",
    },
    {
        "desk_id": "execution",
        "display_name": "Execution Desk",
        "mandate": "Paper orders, broker readiness, live proposals, reconciliation, and kill switch state.",
        "allowed_tools": ["astroq.execution.dry_run"],
        "forbidden_actions": ["code_change"],
        "evidence_required": ["execution_preview", "broker_readiness", "risk_gate"],
        "handoff_targets": ["risk", "reporting"],
        "default_policy": "approval_required_for_orders",
        "status": "available",
    },
    {
        "desk_id": "engineering",
        "display_name": "Engineering Desk",
        "mandate": "CodeGraph, AST, test design diagnostics, bug triage, and work orders.",
        "allowed_tools": ["astroq.health", "astroq.architecture.ast", "astroq.test.design", "astroq.docs.check"],
        "forbidden_actions": ["write_data", "paper_order", "live_order"],
        "evidence_required": ["codegraph", "ast_intelligence", "test_design"],
        "handoff_targets": ["data", "research", "risk", "reporting"],
        "default_policy": "work_order_only",
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
        "evidence_required": ["lifecycle_readiness", "data_status", "strategy_catalog"],
        "handoff_targets": ["data", "research", "risk", "execution", "engineering"],
        "default_policy": "read_only_summary",
        "status": "available",
    },
]


def list_desks() -> list[dict[str, Any]]:
    return [dict(desk) for desk in DESKS]


def get_desk(desk_id: str) -> dict[str, Any] | None:
    for desk in DESKS:
        if desk["desk_id"] == desk_id:
            return dict(desk)
    return None
