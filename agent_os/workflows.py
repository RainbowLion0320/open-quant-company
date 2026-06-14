from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DeskWorkflowPlan:
    desk: str
    answer: str
    confidence: float
    evidence_label: str
    evidence_uri: str
    evidence_summary: str
    action_type: str
    tool_id: str
    risk_level: str
    action_summary: str
    expected_effect: str
    blockers: list[str] = field(default_factory=list)
    handoffs: list[dict[str, Any]] = field(default_factory=list)


_DESK_PROFILES: dict[str, dict[str, str]] = {
    "data": {
        "answer": "Data Desk 已记录 CEO 问题。下一步应先读取本地 DataHub 健康状态，确认缺失、过期和 provider 权限状态后再提出修复。",
        "evidence_label": "DataHub status view",
        "evidence_uri": "/datahub",
        "evidence_summary": "Open DataHub health and source capability details.",
        "action_type": "data_status",
        "tool_id": "astroq.data.status",
        "risk_level": "read_only",
        "action_summary": "Read local DataHub health status.",
        "expected_effect": "Records current data health without writing data.",
    },
    "research": {
        "answer": "Research Desk 已记录 CEO 问题。下一步应读取策略目录和证据状态，再判断哪些策略有足够 OOS、IC/ICIR 或 overlay evidence。",
        "evidence_label": "Strategy Lab",
        "evidence_uri": "/strategy-lab",
        "evidence_summary": "Open strategy catalog and evidence views.",
        "action_type": "strategy_catalog",
        "tool_id": "astroq.strategy.catalog",
        "risk_level": "read_only",
        "action_summary": "Read strategy catalog and promotion layers.",
        "expected_effect": "Records current strategy catalog state without running backtests.",
    },
    "risk": {
        "answer": "Risk Desk 已记录 CEO 问题。下一步应读取 lifecycle readiness，确认数据、策略、风险和执行门禁是否阻断。",
        "evidence_label": "Lifecycle readiness",
        "evidence_uri": "/system?tab=lifecycle",
        "evidence_summary": "Open lifecycle readiness and blocker details.",
        "action_type": "lifecycle_check",
        "tool_id": "astroq.lifecycle.check",
        "risk_level": "read_only",
        "action_summary": "Read lifecycle readiness gates.",
        "expected_effect": "Records current lifecycle readiness without changing configuration or data.",
    },
    "execution": {
        "answer": "Execution Desk 已记录 CEO 问题。下一步只能做 dry-run readiness，不会提交 paper/live order。",
        "evidence_label": "Portfolio and execution",
        "evidence_uri": "/portfolio",
        "evidence_summary": "Open portfolio and execution readiness views.",
        "action_type": "execution_dry_run",
        "tool_id": "astroq.execution.dry_run",
        "risk_level": "dry_run",
        "action_summary": "Run execution dry-run readiness.",
        "expected_effect": "Produces an execution preview without submitting orders.",
    },
    "engineering": {
        "answer": "Engineering Desk 已记录 CEO 问题。下一步应读取 AST diagnostics，识别是否存在真实重复实现或架构风险；Web runtime 不直接改代码。",
        "evidence_label": "AST Intelligence",
        "evidence_uri": "/system?tab=ast",
        "evidence_summary": "Open AST duplicate implementation diagnostics.",
        "action_type": "architecture_ast",
        "tool_id": "astroq.architecture.ast",
        "risk_level": "read_only",
        "action_summary": "Generate or read AST duplicate implementation diagnostics.",
        "expected_effect": "Records architecture diagnostics without editing repository files.",
    },
    "reporting": {
        "answer": "Reporting Desk 已记录 CEO 问题。下一步应先运行生命周期 readiness 只读检查，再把数据、研究和风险 desk 的阻断点汇总成 CEO 简报。",
        "evidence_label": "Lifecycle readiness",
        "evidence_uri": "/system?tab=lifecycle",
        "evidence_summary": "Open lifecycle readiness and blocker details.",
        "action_type": "lifecycle_check",
        "tool_id": "astroq.lifecycle.check",
        "risk_level": "read_only",
        "action_summary": "Read lifecycle readiness for the CEO brief.",
        "expected_effect": "Records current lifecycle readiness without changing configuration or data.",
    },
}


def build_desk_workflow_plan(*, desk: str, content: str) -> DeskWorkflowPlan:
    profile = _DESK_PROFILES.get(desk)
    if profile is None:
        raise ValueError(f"Unknown desk workflow: {desk}")
    return DeskWorkflowPlan(
        desk=desk,
        answer=profile["answer"],
        confidence=_confidence_for(desk),
        evidence_label=profile["evidence_label"],
        evidence_uri=profile["evidence_uri"],
        evidence_summary=profile["evidence_summary"],
        action_type=profile["action_type"],
        tool_id=profile["tool_id"],
        risk_level=profile["risk_level"],
        action_summary=profile["action_summary"],
        expected_effect=profile["expected_effect"],
        handoffs=_handoffs_for(desk, content),
    )


def _confidence_for(desk: str) -> float:
    return 0.68 if desk == "reporting" else 0.64


def _handoffs_for(desk: str, content: str) -> list[dict[str, Any]]:
    normalized = content.lower()
    if desk == "reporting" and _is_daily_brief_request(normalized):
        return [
            {"target_desk": "data", "reason": "CEO daily brief needs current data readiness and blocker status."},
            {"target_desk": "research", "reason": "CEO daily brief needs strategy evidence and promotion status."},
            {"target_desk": "risk", "reason": "CEO daily brief needs lifecycle and execution gate interpretation."},
        ]
    if desk == "research" and any(token in normalized for token in ("数据", "data", "coverage", "缺")):
        return [{"target_desk": "data", "reason": "Research answer depends on data coverage or missing-data evidence."}]
    if desk == "risk" and any(token in normalized for token in ("下单", "order", "执行", "execution")):
        return [{"target_desk": "execution", "reason": "Risk review needs execution readiness details."}]
    if desk == "engineering" and any(token in normalized for token in ("数据", "data", "pipeline")):
        return [{"target_desk": "data", "reason": "Engineering risk may affect data pipeline behavior."}]
    return []


def _is_daily_brief_request(normalized: str) -> bool:
    tokens = ("今天", "日常", "简报", "daily", "brief", "should do", "what should")
    return any(token in normalized for token in tokens)
