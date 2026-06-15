from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


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
    planning_mode: str = "single_intent"
    reasoning: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    handoffs: list[dict[str, Any]] = field(default_factory=list)
    work_orders: list[WorkflowWorkOrderSpec] = field(default_factory=list)


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

_INTENT_PROFILES: dict[str, list[tuple[tuple[str, ...], dict[str, str]]]] = {
    "reporting": [
        (
            ("组合", "portfolio", "持仓", "风险复盘", "执行复盘", "execution review"),
            {
                "answer": "Reporting Desk 已识别到 portfolio operating review。下一步会并行读取 Research 策略证据、Risk 生命周期门禁和 Execution dry-run 预览，再汇总组合层面的 CEO 复盘。",
                "evidence_label": "Portfolio operating review",
                "evidence_uri": "/portfolio",
                "evidence_summary": "Open portfolio, risk, and execution review context.",
                "action_type": "portfolio_review",
                "tool_id": "astroq.lifecycle.check",
                "risk_level": "read_only",
                "action_summary": "Read lifecycle readiness for portfolio review.",
                "expected_effect": "Records portfolio review blockers without changing data, strategy, or orders.",
            },
        ),
    ],
    "data": [
        (
            ("补", "修复", "repair", "backfill", "补齐"),
            {
                "answer": "Data Desk 已识别到补数据请求。下一步会先生成 dry-run 演练动作，确认 provider、权限、覆盖率和写入影响；正式写入动作会进入 CEO 审批队列，不会自动执行。",
                "evidence_label": "Data repair workflow",
                "evidence_uri": "/datahub",
                "evidence_summary": "Open DataHub health, coverage, and repair workflow context.",
                "action_type": "data_repair_plan",
                "tool_id": "astroq.data.repair.dry_run",
                "risk_level": "dry_run",
                "action_summary": "Prepare Data Desk repair dry-run and approval actions.",
                "expected_effect": "Records repair preview and creates an approval-gated write action.",
            },
        ),
        (
            ("数据源", "source", "capability", "registry", "能力", "diff", "差异"),
            {
                "answer": "Data Desk 已识别到数据源能力治理问题。下一步应对比 Source Capability Registry 与项目 data_registry，确认是未接入、权限缺失还是字段/频率口径不一致。",
                "evidence_label": "Data source capability matrix",
                "evidence_uri": "/datahub?tab=sources",
                "evidence_summary": "Open data source capability matrix and registry diff.",
                "action_type": "data_sources_diff",
                "tool_id": "astroq.data.sources.diff_registry",
                "risk_level": "read_only",
                "action_summary": "Compare source capability registry with project data_registry.",
                "expected_effect": "Records capability-vs-registry gaps without downloading data.",
            },
        ),
    ],
    "research": [
        (
            ("阻断", "blocked", "blocker", "missing", "缺数据", "coverage", "lifecycle"),
            {
                "answer": "Research Desk 已识别到 strategy blocker review。下一步会同时读取 strategy competition evidence、DataHub coverage 和 lifecycle gates，用证据区分策略质量不足、数据缺口、样本不足或系统门禁阻断。",
                "evidence_label": "Strategy blocker review",
                "evidence_uri": "/strategy-lab",
                "evidence_summary": "Open strategy evidence, data coverage, and lifecycle blocker context.",
                "action_type": "strategy_blocker_review",
                "tool_id": "astroq.strategy.compete",
                "risk_level": "read_only",
                "action_summary": "Read strategy blocker evidence across Research, Data, and Risk desks.",
                "expected_effect": "Records blocker evidence without changing data, strategy, or configuration.",
            },
        ),
        (
            ("竞争", "compete", "competition", "公平", "12", "oos", "ic/icir", "icir"),
            {
                "answer": "Research Desk 已识别到策略公平竞争问题。下一步应读取统一 strategy competition evidence，检查 OOS、IC/ICIR、样本数和阻断原因。",
                "evidence_label": "Strategy competition evidence",
                "evidence_uri": "/strategy-lab",
                "evidence_summary": "Open strategy competition and evidence views.",
                "action_type": "strategy_competition",
                "tool_id": "astroq.strategy.compete",
                "risk_level": "read_only",
                "action_summary": "Read fair strategy competition evidence.",
                "expected_effect": "Records current strategy competition evidence without changing strategy state.",
            },
        ),
        (
            ("回测", "backtest", "dry-run"),
            {
                "answer": "Research Desk 已识别到回测请求。下一步先创建 backtest dry-run action，确认命令、策略范围和写入影响，再决定是否进入正式回测。",
                "evidence_label": "Backtest evidence",
                "evidence_uri": "/research",
                "evidence_summary": "Open research and backtest evidence views.",
                "action_type": "backtest_dry_run",
                "tool_id": "astroq.backtest.run.dry_run",
                "risk_level": "dry_run",
                "action_summary": "Run backtest dry-run plan.",
                "expected_effect": "Produces a backtest dry-run plan without official evidence writes.",
            },
        ),
    ],
    "engineering": [
        (
            ("bug", "修", "修复", "改代码", "实现", "工单", "codex", "代码"),
            {
                "answer": "Engineering Desk 已识别到代码/bug 请求。Web runtime 不会直接改仓库；下一步会创建工程工单，并附带 AST 与测试设计诊断动作，交给 Codex、Claude 或人工维护者处理。",
                "evidence_label": "Engineering work-order triage",
                "evidence_uri": "/system?tab=ast",
                "evidence_summary": "Open engineering diagnostics and work-order context.",
                "action_type": "engineering_work_order_triage",
                "tool_id": "astroq.architecture.ast",
                "risk_level": "read_only",
                "action_summary": "Run engineering diagnostics for a code-change work order.",
                "expected_effect": "Creates diagnostics evidence and a work order without editing repository files.",
            },
        ),
        (
            ("文档", "docs", "doc", "旧描述", "stale"),
            {
                "answer": "Engineering Desk 已识别到文档一致性问题。下一步应运行 docs check，定位陈旧设计词和文档治理风险；Web runtime 仍不直接改仓库。",
                "evidence_label": "Documentation hygiene",
                "evidence_uri": "/system?tab=tests",
                "evidence_summary": "Open system quality views and documentation hygiene evidence.",
                "action_type": "docs_check",
                "tool_id": "astroq.docs.check",
                "risk_level": "read_only",
                "action_summary": "Run documentation hygiene check.",
                "expected_effect": "Records documentation stale phrase findings without editing files.",
            },
        ),
        (
            ("测试设计", "test design", "test", "测试", "fixture", "mock"),
            {
                "answer": "Engineering Desk 已识别到测试设计审查问题。下一步应运行 test design intelligence，检查测试风险、目标关联、fixture/mock 和断言强度。",
                "evidence_label": "Test design intelligence",
                "evidence_uri": "/system?tab=tests",
                "evidence_summary": "Open test design intelligence diagnostics.",
                "action_type": "test_design",
                "tool_id": "astroq.test.design",
                "risk_level": "read_only",
                "action_summary": "Generate or read test design diagnostics.",
                "expected_effect": "Records test design diagnostics without changing source files.",
            },
        ),
    ],
}


def build_desk_workflow_plan(*, desk: str, content: str) -> DeskWorkflowPlan:
    dynamic_plan = _dynamic_multi_intent_plan(desk=desk, content=content)
    if dynamic_plan is not None:
        return dynamic_plan

    profile = _profile_for(desk, content)
    if profile is None:
        raise ValueError(f"Unknown desk workflow: {desk}")
    normalized = content.lower()
    actions = _actions_for_profile(desk=desk, profile=profile, normalized_content=normalized)
    handoffs = _handoffs_for(desk, content)
    work_orders = _work_orders_for(desk, content)
    planning_mode = "fixed_intent" if len(actions) > 1 else "single_intent"
    return DeskWorkflowPlan(
        desk=desk,
        answer=profile["answer"],
        confidence=_confidence_for(desk),
        actions=actions,
        planning_mode=planning_mode,
        reasoning=_reasoning_for_plan(
            source_desk=desk,
            planning_mode=planning_mode,
            actions=actions,
            handoffs=handoffs,
            work_orders=work_orders,
        ),
        handoffs=handoffs,
        work_orders=work_orders,
    )


def _dynamic_multi_intent_plan(*, desk: str, content: str) -> DeskWorkflowPlan | None:
    normalized = content.lower()
    if desk != "reporting" or _is_daily_brief_request(normalized) or _is_portfolio_review_request(normalized):
        return None

    actions = _dynamic_actions_for_content(normalized)
    if len(actions) < 2:
        return None

    target_desks = _ordered_unique([action.desk for action in actions])
    handoffs = [
        {
            "target_desk": target_desk,
            "reason": f"Dynamic CEO multi-intent plan needs {target_desk.title()} Desk evidence.",
        }
        for target_desk in target_desks
    ]
    return DeskWorkflowPlan(
        desk=desk,
        answer=(
            "Reporting Desk 已生成 dynamic multi-intent / 多意图计划：按 Data、Research、Risk、"
            "Execution 和 Engineering 证据链拆分安全动作，再由 CEO Office 汇总结果。"
        ),
        confidence=0.72,
        actions=actions,
        planning_mode="dynamic_multi_intent",
        reasoning=_reasoning_for_plan(
            source_desk=desk,
            planning_mode="dynamic_multi_intent",
            actions=actions,
            handoffs=handoffs,
            work_orders=[],
        ),
        handoffs=handoffs,
    )


def _dynamic_actions_for_content(normalized: str) -> list[WorkflowActionSpec]:
    actions: list[WorkflowActionSpec] = []

    if _mentions_data_source_gap(normalized):
        actions.append(
            WorkflowActionSpec(
                desk="data",
                action_type="data_sources_diff",
                tool_id="astroq.data.sources.diff_registry",
                risk_level="read_only",
                summary="Compare source capability registry with project data_registry for CEO review.",
                expected_effect="Records capability-vs-registry gaps without downloading data.",
                evidence=WorkflowEvidenceSpec(
                    label="Data source capability matrix",
                    uri="/datahub?tab=sources",
                    summary="Open data source capability matrix and registry diff.",
                ),
            )
        )

    if _mentions_strategy_competition(normalized):
        actions.append(
            WorkflowActionSpec(
                desk="research",
                action_type="strategy_competition",
                tool_id="astroq.strategy.compete",
                risk_level="read_only",
                summary="Read strategy competition evidence for CEO review.",
                expected_effect="Records OOS, IC/ICIR, sample-size, and strategy blocker evidence.",
                evidence=WorkflowEvidenceSpec(
                    label="Strategy competition evidence",
                    uri="/strategy-lab",
                    summary="Open strategy competition and promotion evidence views.",
                ),
            )
        )

    if _mentions_lifecycle(normalized):
        actions.append(
            WorkflowActionSpec(
                desk="risk",
                action_type="lifecycle_check",
                tool_id="astroq.lifecycle.check",
                risk_level="read_only",
                summary="Read lifecycle readiness gates for CEO review.",
                expected_effect="Records lifecycle readiness and blocker evidence without changing system state.",
                evidence=WorkflowEvidenceSpec(
                    label="Lifecycle readiness",
                    uri="/system?tab=lifecycle",
                    summary="Open lifecycle readiness and blocker details.",
                ),
            )
        )

    if _mentions_execution_dry_run(normalized):
        actions.append(
            WorkflowActionSpec(
                desk="execution",
                action_type="execution_dry_run",
                tool_id="astroq.execution.dry_run",
                risk_level="dry_run",
                summary="Run execution dry-run readiness for CEO review.",
                expected_effect="Produces execution readiness preview without submitting paper or live orders.",
                evidence=WorkflowEvidenceSpec(
                    label="Execution readiness",
                    uri="/portfolio",
                    summary="Open portfolio and execution readiness views.",
                ),
            )
        )

    if _mentions_test_design(normalized):
        actions.append(
            WorkflowActionSpec(
                desk="engineering",
                action_type="test_design",
                tool_id="astroq.test.design",
                risk_level="read_only",
                summary="Run test design diagnostics for CEO review.",
                expected_effect="Records test design risk evidence without changing source files.",
                evidence=WorkflowEvidenceSpec(
                    label="Test design intelligence",
                    uri="/system?tab=tests",
                    summary="Open test design intelligence diagnostics.",
                ),
            )
        )

    if _mentions_ast_diagnostics(normalized):
        actions.append(
            WorkflowActionSpec(
                desk="engineering",
                action_type="architecture_ast",
                tool_id="astroq.architecture.ast",
                risk_level="read_only",
                summary="Run AST diagnostics for CEO review.",
                expected_effect="Records duplicate implementation and architecture risk evidence without editing source files.",
                evidence=WorkflowEvidenceSpec(
                    label="AST Intelligence",
                    uri="/system?tab=ast",
                    summary="Open AST duplicate implementation diagnostics.",
                ),
            )
        )

    return _dedupe_actions(actions)


def _profile_for(desk: str, content: str) -> dict[str, str] | None:
    normalized = content.lower()
    for triggers, profile in _INTENT_PROFILES.get(desk, []):
        if any(trigger in normalized for trigger in triggers):
            return profile
    return _DESK_PROFILES.get(desk)


def _confidence_for(desk: str) -> float:
    return 0.68 if desk == "reporting" else 0.64


def _actions_for_profile(*, desk: str, profile: dict[str, str], normalized_content: str) -> list[WorkflowActionSpec]:
    if desk == "data" and _is_data_repair_request(normalized_content):
        table = _extract_repair_table(normalized_content)
        if table:
            return [
                WorkflowActionSpec(
                    desk="data",
                    action_type="data_repair_dry_run",
                    tool_id="astroq.data.repair.dry_run",
                    risk_level="dry_run",
                    summary=f"Dry-run Data Desk repair plan for {table}.",
                    expected_effect="Runs a non-writing data repair preview and records provider/data blockers.",
                    parameters={"table": table},
                    evidence=WorkflowEvidenceSpec(
                        label="Data repair dry-run",
                        uri="/datahub",
                        summary="Open DataHub health and repair preview context.",
                    ),
                ),
                WorkflowActionSpec(
                    desk="data",
                    action_type="data_repair",
                    tool_id="astroq.data.repair",
                    risk_level="write_data",
                    summary=f"Repair DataHub dimension {table} after CEO approval.",
                    expected_effect="Writes repaired DataHub partitions only after explicit CEO approval and provider success.",
                    parameters={"table": table},
                    evidence=WorkflowEvidenceSpec(
                        label="Data repair approval",
                        uri="/datahub",
                        summary="Open DataHub health, coverage, and repair approval context.",
                    ),
                ),
            ]
    if desk == "research" and _is_strategy_blocker_request(normalized_content):
        return [
            WorkflowActionSpec(
                desk="research",
                action_type="strategy_competition",
                tool_id="astroq.strategy.compete",
                risk_level="read_only",
                summary="Read Research Desk strategy competition blockers.",
                expected_effect="Records OOS, IC/ICIR, sample-size, and strategy blocker evidence without changing strategy state.",
                evidence=WorkflowEvidenceSpec(
                    label="Strategy competition evidence",
                    uri="/strategy-lab",
                    summary="Open strategy competition and promotion blocker evidence.",
                ),
            ),
            WorkflowActionSpec(
                desk="data",
                action_type="data_status",
                tool_id="astroq.data.status",
                risk_level="read_only",
                summary="Read Data Desk coverage and freshness blockers for strategy review.",
                expected_effect="Records local DataHub health without repairing or downloading data.",
                evidence=WorkflowEvidenceSpec(
                    label="DataHub status view",
                    uri="/datahub",
                    summary="Open data coverage, freshness, and source capability blockers.",
                ),
            ),
            WorkflowActionSpec(
                desk="risk",
                action_type="lifecycle_check",
                tool_id="astroq.lifecycle.check",
                risk_level="read_only",
                summary="Read Risk Desk lifecycle gates for strategy blocker review.",
                expected_effect="Records lifecycle readiness and risk blockers without changing system state.",
                evidence=WorkflowEvidenceSpec(
                    label="Lifecycle readiness",
                    uri="/system?tab=lifecycle",
                    summary="Open lifecycle readiness and blocker details.",
                ),
            ),
        ]
    if desk == "engineering" and _is_engineering_code_request(normalized_content):
        return [
            WorkflowActionSpec(
                desk="engineering",
                action_type="architecture_ast",
                tool_id="astroq.architecture.ast",
                risk_level="read_only",
                summary="Run AST diagnostics for engineering work-order triage.",
                expected_effect="Records duplicate implementation and architecture risk evidence without editing repository files.",
                evidence=WorkflowEvidenceSpec(
                    label="AST Intelligence",
                    uri="/system?tab=ast",
                    summary="Open AST duplicate implementation diagnostics.",
                ),
            ),
            WorkflowActionSpec(
                desk="engineering",
                action_type="test_design",
                tool_id="astroq.test.design",
                risk_level="read_only",
                summary="Run test design diagnostics for engineering work-order triage.",
                expected_effect="Records test design risk evidence without editing repository files.",
                evidence=WorkflowEvidenceSpec(
                    label="Test design intelligence",
                    uri="/system?tab=tests",
                    summary="Open test design intelligence diagnostics.",
                ),
            ),
        ]
    if desk == "reporting" and _is_daily_brief_request(normalized_content):
        return [
            WorkflowActionSpec(
                desk="data",
                action_type="data_status",
                tool_id="astroq.data.status",
                risk_level="read_only",
                summary="Read Data Desk health for the CEO daily brief.",
                expected_effect="Records data health and blocker evidence without writing data.",
                evidence=WorkflowEvidenceSpec(
                    label="DataHub status view",
                    uri="/datahub",
                    summary="Open DataHub health and source capability details.",
                ),
            ),
            WorkflowActionSpec(
                desk="research",
                action_type="strategy_catalog",
                tool_id="astroq.strategy.catalog",
                risk_level="read_only",
                summary="Read Research Desk strategy catalog for the CEO daily brief.",
                expected_effect="Records strategy layer and promotion status without running backtests.",
                evidence=WorkflowEvidenceSpec(
                    label="Strategy Lab",
                    uri="/strategy-lab",
                    summary="Open strategy catalog and evidence views.",
                ),
            ),
            WorkflowActionSpec(
                desk="risk",
                action_type="lifecycle_check",
                tool_id="astroq.lifecycle.check",
                risk_level="read_only",
                summary="Read Risk Desk lifecycle gates for the CEO daily brief.",
                expected_effect="Records lifecycle readiness and blocker evidence without changing system state.",
                evidence=WorkflowEvidenceSpec(
                    label="Lifecycle readiness",
                    uri="/system?tab=lifecycle",
                    summary="Open lifecycle readiness and blocker details.",
                ),
            ),
        ]
    if desk == "reporting" and _is_portfolio_review_request(normalized_content):
        return [
            WorkflowActionSpec(
                desk="research",
                action_type="strategy_competition",
                tool_id="astroq.strategy.compete",
                risk_level="read_only",
                summary="Read Research Desk strategy competition evidence for portfolio review.",
                expected_effect="Records current strategy evidence, OOS, IC/ICIR, and blockers without changing strategy state.",
                evidence=WorkflowEvidenceSpec(
                    label="Strategy competition evidence",
                    uri="/strategy-lab",
                    summary="Open strategy competition and promotion evidence views.",
                ),
            ),
            WorkflowActionSpec(
                desk="risk",
                action_type="lifecycle_check",
                tool_id="astroq.lifecycle.check",
                risk_level="read_only",
                summary="Read Risk Desk lifecycle gates for portfolio review.",
                expected_effect="Records lifecycle readiness and blocker evidence without changing system state.",
                evidence=WorkflowEvidenceSpec(
                    label="Lifecycle readiness",
                    uri="/system?tab=lifecycle",
                    summary="Open lifecycle readiness and blocker details.",
                ),
            ),
            WorkflowActionSpec(
                desk="execution",
                action_type="execution_dry_run",
                tool_id="astroq.execution.dry_run",
                risk_level="dry_run",
                summary="Run Execution Desk dry-run readiness for portfolio review.",
                expected_effect="Produces execution readiness preview without submitting paper or live orders.",
                evidence=WorkflowEvidenceSpec(
                    label="Execution readiness",
                    uri="/portfolio",
                    summary="Open portfolio and execution readiness views.",
                ),
            ),
        ]
    return [_action_for_profile(desk=desk, profile=profile)]


def _action_for_profile(*, desk: str, profile: dict[str, str]) -> WorkflowActionSpec:
    return WorkflowActionSpec(
        desk=desk,
        action_type=profile["action_type"],
        tool_id=profile["tool_id"],
        risk_level=profile["risk_level"],
        summary=profile["action_summary"],
        expected_effect=profile["expected_effect"],
        evidence=WorkflowEvidenceSpec(
            label=profile["evidence_label"],
            uri=profile["evidence_uri"],
            summary=profile["evidence_summary"],
        ),
    )


def _reasoning_for_plan(
    *,
    source_desk: str,
    planning_mode: str,
    actions: list[WorkflowActionSpec],
    handoffs: list[dict[str, Any]],
    work_orders: list[WorkflowWorkOrderSpec],
) -> list[dict[str, Any]]:
    tool_ids = _ordered_unique([action.tool_id for action in actions])
    target_desks = _ordered_unique([action.desk for action in actions])
    approval_required_count = sum(1 for action in actions if action.risk_level not in {"read_only", "dry_run"})
    return [
        {
            "kind": "intent_match",
            "source_desk": source_desk,
            "planning_mode": planning_mode,
            "target_desks": target_desks,
        },
        {
            "kind": "tool_plan",
            "tool_count": len(tool_ids),
            "tool_ids": tool_ids,
            "desk_count": len(target_desks),
            "risk_levels": _ordered_unique([action.risk_level for action in actions]),
        },
        {
            "kind": "safety",
            "approval_required_count": approval_required_count,
            "auto_runnable_count": len(actions) - approval_required_count,
            "writes_blocked_by_policy": approval_required_count > 0,
        },
        {
            "kind": "evidence_plan",
            "evidence_routes": _ordered_unique([action.evidence.uri for action in actions]),
            "handoff_count": len(handoffs),
            "work_order_count": len(work_orders),
        },
    ]


def _handoffs_for(desk: str, content: str) -> list[dict[str, Any]]:
    normalized = content.lower()
    if desk == "research" and _is_strategy_blocker_request(normalized):
        return [
            {"target_desk": "data", "reason": "Strategy blocker review needs DataHub coverage and freshness evidence."},
            {"target_desk": "risk", "reason": "Strategy blocker review needs lifecycle and risk-gate interpretation."},
        ]
    if desk == "reporting" and _is_daily_brief_request(normalized):
        return [
            {"target_desk": "data", "reason": "CEO daily brief needs current data readiness and blocker status."},
            {"target_desk": "research", "reason": "CEO daily brief needs strategy evidence and promotion status."},
            {"target_desk": "risk", "reason": "CEO daily brief needs lifecycle and execution gate interpretation."},
        ]
    if desk == "reporting" and _is_portfolio_review_request(normalized):
        return [
            {"target_desk": "research", "reason": "Portfolio review needs current strategy competition evidence."},
            {"target_desk": "risk", "reason": "Portfolio review needs lifecycle and risk gate interpretation."},
            {"target_desk": "execution", "reason": "Portfolio review needs execution dry-run readiness."},
        ]
    if desk == "research" and any(token in normalized for token in ("数据", "data", "coverage", "缺")):
        return [{"target_desk": "data", "reason": "Research answer depends on data coverage or missing-data evidence."}]
    if desk == "risk" and any(token in normalized for token in ("下单", "order", "执行", "execution")):
        return [{"target_desk": "execution", "reason": "Risk review needs execution readiness details."}]
    if desk == "engineering" and any(token in normalized for token in ("数据", "data", "pipeline")):
        return [{"target_desk": "data", "reason": "Engineering risk may affect data pipeline behavior."}]
    return []


def _work_orders_for(desk: str, content: str) -> list[WorkflowWorkOrderSpec]:
    normalized = content.lower()
    if desk != "engineering" or not _is_engineering_code_request(normalized):
        return []
    affected_files = _extract_file_paths(content)
    subject = affected_files[0] if affected_files else "engineering request"
    return [
        WorkflowWorkOrderSpec(
            title=f"Investigate {subject}",
            summary="Engineering Desk captured a code or bug request for an external coding agent or human maintainer.",
            impact="Keeps repository edits outside the Web runtime while preserving a traceable CEO request and diagnostic evidence.",
            affected_files=affected_files,
            suggested_verification=_suggested_verification_for_paths(affected_files),
        )
    ]


def _is_daily_brief_request(normalized: str) -> bool:
    tokens = ("今天", "日常", "简报", "daily", "brief", "should do", "what should")
    return any(token in normalized for token in tokens)


def _is_portfolio_review_request(normalized: str) -> bool:
    tokens = ("组合", "portfolio", "持仓", "风险复盘", "执行复盘", "execution review")
    return any(token in normalized for token in tokens)


def _is_data_repair_request(normalized: str) -> bool:
    tokens = ("补", "修复", "repair", "backfill", "补齐")
    return any(token in normalized for token in tokens)


def _is_strategy_blocker_request(normalized: str) -> bool:
    strategy_tokens = ("策略", "strategy")
    blocker_tokens = ("阻断", "blocked", "blocker", "missing", "缺数据", "coverage", "lifecycle")
    return any(token in normalized for token in strategy_tokens) and any(token in normalized for token in blocker_tokens)


def _is_engineering_code_request(normalized: str) -> bool:
    code_tokens = ("bug", "修", "修复", "改代码", "实现", "工单", "codex", "代码")
    return any(token in normalized for token in code_tokens)


def _mentions_data_source_gap(normalized: str) -> bool:
    tokens = ("数据源", "source", "registry", "capability", "能力", "diff", "差异", "data_registry")
    return any(token in normalized for token in tokens)


def _mentions_strategy_competition(normalized: str) -> bool:
    tokens = ("12", "策略", "strategy", "compete", "competition", "公平", "oos", "ic/icir", "icir")
    return any(token in normalized for token in tokens)


def _mentions_lifecycle(normalized: str) -> bool:
    tokens = ("lifecycle", "生命周期", "门禁", "gate", "readiness", "阻断")
    return any(token in normalized for token in tokens)


def _mentions_execution_dry_run(normalized: str) -> bool:
    tokens = ("execution dry-run", "execution dry run", "执行 dry-run", "执行 dry run", "执行演练")
    return any(token in normalized for token in tokens)


def _mentions_test_design(normalized: str) -> bool:
    tokens = ("测试设计", "test design", "fixture", "mock", "断言", "测试风险")
    return any(token in normalized for token in tokens)


def _mentions_ast_diagnostics(normalized: str) -> bool:
    tokens = ("ast", "重复实现", "重复造轮子", "架构风险", "architecture")
    return any(token in normalized for token in tokens)


def _dedupe_actions(actions: list[WorkflowActionSpec]) -> list[WorkflowActionSpec]:
    deduped: list[WorkflowActionSpec] = []
    seen: set[tuple[str, str]] = set()
    for action in actions:
        key = (action.desk, action.tool_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped


def _ordered_unique(values: list[str]) -> list[str]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return unique


def _extract_repair_table(normalized: str) -> str | None:
    ignored = {
        "api",
        "backfill",
        "ceo",
        "data",
        "dry",
        "json",
        "repair",
        "run",
        "table",
    }
    candidates = [match.group(0) for match in re.finditer(r"[a-z][a-z0-9_]{2,}", normalized)]
    for candidate in candidates:
        if "_" in candidate and candidate not in ignored:
            return candidate
    for candidate in candidates:
        if candidate not in ignored:
            return candidate
    return None


def _extract_file_paths(content: str) -> list[str]:
    pattern = re.compile(
        r"(?:(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|mjs|vue|css|md|yaml|yml|json|toml)|[A-Za-z0-9_.-]+\.(?:py|ts|tsx|js|mjs|vue|css|md|yaml|yml|json|toml))"
    )
    paths: list[str] = []
    for match in pattern.finditer(content):
        path = match.group(0).strip("`'\"，。,. ")
        if path and path not in paths:
            paths.append(path)
    return paths


def _suggested_verification_for_paths(paths: list[str]) -> list[str]:
    commands: list[str] = []
    for path in paths:
        if path.startswith("tests/") and path.endswith(".py"):
            commands.append(f".venv/bin/python -m pytest {path} -q")
    if any(path.endswith(".py") for path in paths):
        commands.append(".venv/bin/ruff check agent_os tests --select E9,F63,F7,F82")
    if any(path.endswith((".ts", ".tsx", ".vue", ".css")) or path.startswith("web/frontend/") for path in paths):
        commands.append("cd web/frontend && npm run typecheck")
    if not commands:
        commands.append(".venv/bin/python -m pytest tests/test_agent_os_contracts.py -q")
    deduped: list[str] = []
    for command in commands:
        if command not in deduped:
            deduped.append(command)
    return deduped
