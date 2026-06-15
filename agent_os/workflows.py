from __future__ import annotations

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


@dataclass(frozen=True)
class DeskWorkflowPlan:
    desk: str
    answer: str
    confidence: float
    actions: list[WorkflowActionSpec]
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

_INTENT_PROFILES: dict[str, list[tuple[tuple[str, ...], dict[str, str]]]] = {
    "data": [
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
    profile = _profile_for(desk, content)
    if profile is None:
        raise ValueError(f"Unknown desk workflow: {desk}")
    normalized = content.lower()
    actions = _actions_for_profile(desk=desk, profile=profile, normalized_content=normalized)
    return DeskWorkflowPlan(
        desk=desk,
        answer=profile["answer"],
        confidence=_confidence_for(desk),
        actions=actions,
        handoffs=_handoffs_for(desk, content),
    )


def _profile_for(desk: str, content: str) -> dict[str, str] | None:
    normalized = content.lower()
    for triggers, profile in _INTENT_PROFILES.get(desk, []):
        if any(trigger in normalized for trigger in triggers):
            return profile
    return _DESK_PROFILES.get(desk)


def _confidence_for(desk: str) -> float:
    return 0.68 if desk == "reporting" else 0.64


def _actions_for_profile(*, desk: str, profile: dict[str, str], normalized_content: str) -> list[WorkflowActionSpec]:
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
