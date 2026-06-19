from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any

from agent_os.tool_planner import ToolPlanningAgent


@dataclass(frozen=True)
class WorkflowEvidenceSpec:
    label: str
    uri: str
    summary: str


@dataclass(frozen=True)
class WorkflowActionSpec:
    desk: str
    action_type: str
    tool_id: str
    risk_level: str
    summary: str
    expected_effect: str
    evidence: WorkflowEvidenceSpec
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowWorkOrderSpec:
    title: str
    summary: str
    impact: str
    affected_files: list[str]
    suggested_verification: list[str]


@dataclass(frozen=True)
class DeskWorkflowPlan:
    desk: str
    answer: str
    confidence: float
    actions: list[WorkflowActionSpec]
    planning_mode: str = "llm_tool_planning"
    reasoning: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    handoffs: list[dict[str, Any]] = field(default_factory=list)
    work_orders: list[WorkflowWorkOrderSpec] = field(default_factory=list)


@dataclass(frozen=True)
class DeskRoutingDecision:
    assigned_desk: str
    confidence: float
    matched_terms: list[str]
    reason: str
    explicit: bool = False

    def to_reasoning(self) -> dict[str, Any]:
        return {
            "kind": "desk_routing",
            "assigned_desk": self.assigned_desk,
            "confidence": self.confidence,
            "matched_terms": list(self.matched_terms),
            "reason": self.reason,
            "explicit": self.explicit,
        }


def build_desk_workflow_plan(
    *,
    desk: str,
    content: str,
    artifact_context: dict[str, Any] | None = None,
    session_context: dict[str, Any] | None = None,
    router_reasoning: dict[str, Any] | None = None,
) -> DeskWorkflowPlan:
    """Build a CEO workflow plan from provider-selected fixed tools only."""
    result = ToolPlanningAgent().plan(
        desk=desk,
        content=content,
        router_reasoning=router_reasoning or {},
        artifact_context=artifact_context or {},
        session_context=session_context or {},
    )
    actions = [
        WorkflowActionSpec(
            desk=action.desk,
            action_type=action.action_type,
            tool_id=action.tool_id,
            risk_level=action.risk_level,
            summary=action.summary,
            expected_effect=action.expected_effect,
            parameters=dict(action.parameters),
            evidence=_evidence_for_tool(action.tool_id),
        )
        for action in result.actions
    ]
    return DeskWorkflowPlan(
        desk=result.desk,
        answer="",
        confidence=result.confidence,
        actions=actions,
        planning_mode=result.planning_mode,
        reasoning=[result.reasoning],
        blockers=list(result.blockers),
        handoffs=[],
        work_orders=[],
    )


def _evidence_for_tool(tool_id: str) -> WorkflowEvidenceSpec:
    known = {
        "astroq.health": ("Project health", "/system", "Open project health status."),
        "astroq.lifecycle.check": (
            "Lifecycle readiness",
            "/system?tab=lifecycle",
            "Open lifecycle readiness evidence.",
        ),
        "astroq.execution.dry_run": ("Execution dry-run", "/portfolio", "Open execution dry-run evidence."),
        "astroq.agent.live.readiness": (
            "MiniQMT/QMT live readiness",
            "/portfolio",
            "Open live execution readiness evidence.",
        ),
        "astroq.architecture.ast": ("AST intelligence", "/system?tab=ast", "Open AST intelligence diagnostics."),
        "astroq.test.design": ("Test design intelligence", "/system?tab=tests", "Open test design diagnostics."),
        "astroq.docs.check": ("Documentation hygiene", "/system", "Open documentation hygiene diagnostics."),
        "astroq.data.status": ("Data status", "/datahub", "Open DataHub health and coverage status."),
        "astroq.data.sources": (
            "Data source capability summary",
            "/datahub?tab=sources",
            "Open discovered, probed, contracted, and integrated data source capability summary.",
        ),
        "astroq.data.sources.diff_registry": (
            "Data source registry diff",
            "/datahub?tab=sources",
            "Open source capability registry and project data_registry diff.",
        ),
        "astroq.strategy.catalog": ("Strategy catalog", "/strategy-lab", "Open strategy catalog evidence."),
        "astroq.strategy.compete": (
            "Strategy competition evidence",
            "/strategy-lab",
            "Open strategy competition evidence.",
        ),
        "astroq.backtest.run.dry_run": ("Backtest dry-run", "/strategy-lab", "Open backtest dry-run evidence."),
        "astroq.agent.report.daily": ("CEO report artifact", "/", "Open CEO report artifact evidence."),
        "astroq.data.repair": ("Data repair approval", "/datahub", "Open DataHub repair approval context."),
        "astroq.data.repair.dry_run": ("Data repair dry-run", "/datahub", "Open DataHub repair preview context."),
    }
    label, uri, summary = known.get(tool_id, (tool_id, "/", "Open fixed tool evidence."))
    return WorkflowEvidenceSpec(label=label, uri=uri, summary=summary)
