from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent_os.tools import DEFAULT_TOOLS


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


@dataclass(frozen=True)
class SemanticWorkflowDraft:
    answer: str
    confidence: float
    actions: list[dict[str, Any]]
    reasoning: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)


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
            "matched_terms": self.matched_terms,
            "reason": self.reason,
            "explicit": self.explicit,
        }


_DESK_ROUTING_TERMS: dict[str, tuple[str, ...]] = {
    "data": (
        "数据源",
        "数据源能力",
        "数据源矩阵",
        "能力目录",
        "能力页面",
        "补数",
        "补齐",
        "datahub",
        "tushare",
        "akshare",
        "coverage",
        "freshness",
        "字段缺失",
        "表缺失",
        "数据缺口",
        "数据不全",
        "source capability",
        "data registry",
        "data source",
        "backfill",
        "全量探测",
        "样本探测",
        "300条",
    ),
    "research": (
        "策略",
        "因子",
        "回测",
        "oos",
        "ic/icir",
        "icir",
        "技术面",
        "情绪面",
        "基本面",
        "机器学习",
        "ml",
        "alpha",
        "factor",
        "backtest",
        "strategy",
    ),
    "portfolio": (
        "组合",
        "持仓",
        "仓位",
        "权重",
        "调仓",
        "策略组合",
        "rebalance",
        "allocation",
        "position sizing",
        "portfolio",
        "weights",
    ),
    "risk": (
        "风险",
        "回撤",
        "最大回撤",
        "var",
        "cvar",
        "暴露",
        "风控门",
        "生命周期阻断",
        "风险阻断",
        "risk",
        "drawdown",
        "exposure",
    ),
    "execution": (
        "下单",
        "订单",
        "成交",
        "撤单",
        "买入",
        "卖出",
        "委托",
        "交易",
        "paper",
        "live",
        "qmt",
        "miniqmt",
        "券商",
        "交易执行",
        "执行链路",
        "执行演练",
        "order",
        "broker",
        "submit",
        "cancel order",
    ),
    "engineering": (
        "bug",
        "代码",
        "前端",
        "页面",
        "测试",
        "构建",
        "文档",
        "工程诊断",
        "冗余",
        "报错",
        "ceo office",
        "ceo办公室",
        "ceo 办公室",
        "ui",
        "ux",
        "界面",
        "交互",
        "消息",
        "对话",
        "回复",
        "气泡",
        "标签",
        "输入框",
        "时间",
        "斜杠",
        "按钮",
        "状态卡",
        "状态栏",
        "右侧",
        "左侧",
        "标记",
        "显示",
        "typecheck",
        "build",
        "docs",
        "test",
        "frontend",
    ),
    "reporting": (
        "日报",
        "总结",
        "全局状态",
        "优先级",
        "下一步",
        "今天",
        "简报",
        "复盘",
        "汇总",
        "daily",
        "brief",
        "summary",
        "priority",
        "hello",
        "hi",
        "你好",
        "帮助",
        "你能做什么",
    ),
}

_DESK_ROUTING_TERM_WEIGHTS: dict[str, float] = {
    "数据源": 2.5,
    "数据源能力": 3.0,
    "数据源矩阵": 3.0,
    "能力目录": 2.5,
    "能力页面": 2.5,
    "全量探测": 2.5,
    "样本探测": 2.5,
    "300条": 2.0,
    "买入": 2.5,
    "卖出": 2.5,
    "委托": 2.5,
    "交易": 1.8,
    "执行链路": 2.2,
    "执行演练": 2.2,
    "ceo office": 2.5,
    "ceo办公室": 2.5,
    "ceo 办公室": 2.5,
    "消息": 1.6,
    "对话": 1.8,
    "回复": 1.8,
    "气泡": 1.6,
    "标签": 1.4,
    "输入框": 1.8,
    "斜杠": 1.8,
    "状态卡": 1.8,
    "状态栏": 1.8,
    "按钮": 1.4,
    "界面": 1.2,
    "交互": 1.2,
    "显示": 0.8,
    "右侧": 0.8,
    "左侧": 0.8,
    "标记": 1.0,
    "hello": 1.5,
    "hi": 1.5,
    "你好": 1.5,
    "帮助": 1.5,
    "你能做什么": 2.0,
}


def route_ceo_message_desk(content: str) -> DeskRoutingDecision:
    normalized = content.lower()
    matches: dict[str, list[str]] = {}
    scores: dict[str, float] = {}
    for desk, terms in _DESK_ROUTING_TERMS.items():
        desk_matches = [term for term in terms if term.lower() in normalized]
        if desk_matches:
            matches[desk] = desk_matches
            scores[desk] = sum(_DESK_ROUTING_TERM_WEIGHTS.get(term.lower(), _DESK_ROUTING_TERM_WEIGHTS.get(term, 1.0)) for term in desk_matches)

    if not matches:
        return DeskRoutingDecision(
            assigned_desk="reporting",
            confidence=0.4,
            matched_terms=[],
            reason="low_confidence_default_to_reporting",
        )

    ranked = sorted(matches.items(), key=lambda item: (-scores[item[0]], -len(item[1]), item[0]))
    top_desk, top_terms = ranked[0]
    top_score = scores[top_desk]
    tied_desks = [desk for desk, _terms in ranked if abs(scores[desk] - top_score) < 1e-9]
    if len(tied_desks) > 1:
        all_terms: list[str] = []
        for desk in tied_desks:
            all_terms.extend(matches[desk])
        return DeskRoutingDecision(
            assigned_desk="reporting",
            confidence=0.52,
            matched_terms=sorted(set(all_terms)),
            reason=f"cross_desk_tie:{','.join(tied_desks)}",
        )

    confidence = min(0.9, 0.54 + top_score * 0.06)
    return DeskRoutingDecision(
        assigned_desk=top_desk,
        confidence=round(confidence, 2),
        matched_terms=top_terms,
        reason=f"matched_{top_desk}_routing_terms",
    )


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
        "answer": "Research Desk 已记录 CEO 问题。下一步应读取策略目录和证据状态，在技术面、情绪面、基本面、因子和 ML 研究能力内判断哪些策略有足够 OOS、IC/ICIR 或 overlay evidence。",
        "evidence_label": "Strategy Lab",
        "evidence_uri": "/strategy-lab",
        "evidence_summary": "Open strategy catalog and evidence views.",
        "action_type": "strategy_catalog",
        "tool_id": "astroq.strategy.catalog",
        "risk_level": "read_only",
        "action_summary": "Read strategy catalog and promotion layers.",
        "expected_effect": "Records current strategy catalog state without running backtests.",
    },
    "portfolio": {
        "answer": "Portfolio Desk 已记录 CEO 问题。下一步应读取策略证据、生命周期门禁和执行 dry-run 预览，用现有 evidence 判断组合权重、仓位约束、调仓节奏和策略组合优先级；不会生成假目标权重或直接下单。",
        "evidence_label": "Portfolio decision workspace",
        "evidence_uri": "/portfolio",
        "evidence_summary": "Open portfolio, risk, and execution review context.",
        "action_type": "portfolio_decision_review",
        "tool_id": "astroq.strategy.compete",
        "risk_level": "read_only",
        "action_summary": "Read strategy evidence for portfolio-level decision review.",
        "expected_effect": "Records strategy and signal evidence for portfolio decisions without creating target weights or orders.",
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
            ("generate report", "report artifact", "生成报告", "生成 daily", "生成 ceo 简报", "生成简报"),
            {
                "answer": "Reporting Desk 已识别到 daily CEO brief report artifact 生成请求。下一步会创建写本地 report artifact 的审批动作；未获 CEO 审批前不会自动写报告。",
                "evidence_label": "CEO report artifacts",
                "evidence_uri": "/",
                "evidence_summary": "Open CEO Office report cards and artifact evidence.",
                "action_type": "agent_report_daily",
                "tool_id": "astroq.agent.report.daily",
                "risk_level": "write_artifact",
                "action_summary": "Generate a daily CEO brief report artifact after CEO approval.",
                "expected_effect": "Writes a local evidence-cited CEO report artifact only after explicit approval.",
            },
        ),
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
            ("技术面", "technical", "技术指标", "趋势", "动量", "均线", "量价", "突破", "情绪", "sentiment", "资金流", "涨跌停", "龙虎榜", "基本面", "fundamental", "因子", "factor", "ml", "机器学习"),
            {
                "answer": "Research Desk 已识别到研究能力请求。技术面、情绪面、基本面、因子和 ML 都是 Research Desk 的子能力；下一步读取策略目录和证据状态，不把这些研究来源拆成新的一级 desk。",
                "evidence_label": "Strategy Lab",
                "evidence_uri": "/strategy-lab",
                "evidence_summary": "Open strategy catalog, factor evidence, and research views.",
                "action_type": "research_capability_review",
                "tool_id": "astroq.strategy.catalog",
                "risk_level": "read_only",
                "action_summary": "Read strategy catalog for research capability review.",
                "expected_effect": "Records research capability context without running backtests or changing strategy state.",
            },
        ),
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
    "portfolio": [
        (
            ("组合", "portfolio", "持仓", "权重", "调仓", "仓位", "策略组合", "rebalance", "allocation", "weight", "weights", "position sizing"),
            {
                "answer": "Portfolio Desk 已识别到组合决策请求。下一步只读取策略证据、风险门禁和执行演练，判断组合层面的权重、仓位、调仓节奏和策略优先级；缺 evidence 时会返回阻断，不生成假组合建议。",
                "evidence_label": "Portfolio decision workspace",
                "evidence_uri": "/portfolio",
                "evidence_summary": "Open portfolio, strategy evidence, risk gates, and execution readiness.",
                "action_type": "portfolio_decision_review",
                "tool_id": "astroq.strategy.compete",
                "risk_level": "read_only",
                "action_summary": "Read strategy competition evidence for portfolio allocation review.",
                "expected_effect": "Records portfolio decision evidence without creating target weights or submitting orders.",
            },
        ),
    ],
    "engineering": [
        (
            ("ceo office", "ceo办公室", "ceo 办公室", "消息", "对话", "回复", "运营报告部", "分诊", "路由", "标签", "输入框", "时间", "斜杠", "按钮", "状态卡", "状态栏", "ui", "ux", "界面", "交互", "显示"),
            {
                "answer": "Engineering Desk 已识别到 CEO Office 对话/分诊/UI 问题。下一步应检查前端消息展示、自动部门分诊、API 返回的 desk_response，以及 provider semantic 是否被启用或失败；Web runtime 不直接改仓库。",
                "evidence_label": "CEO Office engineering diagnostics",
                "evidence_uri": "/system?tab=ast",
                "evidence_summary": "Open engineering diagnostics for CEO Office routing and message rendering.",
                "action_type": "ceo_office_diagnostics",
                "tool_id": "astroq.architecture.ast",
                "risk_level": "read_only",
                "action_summary": "Inspect CEO Office routing and message rendering diagnostics.",
                "expected_effect": "Records engineering diagnostics without editing repository files.",
            },
        ),
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
    "execution": [
        (
            ("miniqmt", "qmt", "live readiness", "broker readiness", "kill switch", "实盘", "券商", "终端"),
            {
                "answer": "Execution Desk 已识别到 MiniQMT/QMT live readiness 问题。下一步只读取 live readiness、broker readiness 和 kill switch 状态；不会提交 paper/live order。",
                "evidence_label": "MiniQMT/QMT live readiness",
                "evidence_uri": "/portfolio",
                "evidence_summary": "Open broker readiness, live execution, and kill switch context.",
                "action_type": "live_readiness",
                "tool_id": "astroq.agent.live.readiness",
                "risk_level": "read_only",
                "action_summary": "Read MiniQMT/QMT live readiness and kill-switch status.",
                "expected_effect": "Records live readiness blockers without submitting paper or live orders.",
            },
        ),
    ],
}


def build_desk_workflow_plan(
    *,
    desk: str,
    content: str,
    artifact_context: dict[str, Any] | None = None,
    session_context: dict[str, Any] | None = None,
    semantic_planner: Any | None = None,
) -> DeskWorkflowPlan:
    semantic_plan = _semantic_assisted_plan(
        desk=desk,
        content=content,
        artifact_context=artifact_context or {},
        session_context=session_context or {},
        semantic_planner=semantic_planner,
    )
    if semantic_plan is not None:
        return semantic_plan

    conversation_plan = _conversation_plan(desk=desk, content=content)
    if conversation_plan is not None:
        return conversation_plan

    hybrid_plan = _adaptive_artifact_plan(
        desk=desk,
        content=content,
        artifact_context=artifact_context or {},
        session_context=session_context or {},
    )
    if hybrid_plan is not None:
        return hybrid_plan

    adaptive_plan = _adaptive_session_plan(desk=desk, content=content, session_context=session_context or {})
    if adaptive_plan is not None:
        return adaptive_plan

    artifact_plan = _artifact_aware_plan(desk=desk, content=content, artifact_context=artifact_context or {})
    if artifact_plan is not None:
        return artifact_plan

    dynamic_plan = _dynamic_multi_intent_plan(
        desk=desk,
        content=content,
        artifact_context=artifact_context or {},
    )
    if dynamic_plan is not None:
        return dynamic_plan

    open_plan = _open_ended_adaptive_plan(
        desk=desk,
        content=content,
        artifact_context=artifact_context or {},
    )
    if open_plan is not None:
        return open_plan

    profile = _profile_for(desk, content)
    if profile is None:
        raise ValueError(f"Unknown desk workflow: {desk}")
    normalized = content.lower()
    actions = _actions_for_profile(
        desk=desk,
        profile=profile,
        normalized_content=normalized,
        session_context=session_context or {},
    )
    handoffs = _handoffs_for(desk, content)
    work_orders = _work_orders_for(desk, content)
    planning_mode = "fixed_intent" if len(actions) > 1 else "single_intent"
    answer = profile["answer"]
    reasoning = _reasoning_for_plan(
        source_desk=desk,
        planning_mode=planning_mode,
        actions=actions,
        handoffs=handoffs,
        work_orders=work_orders,
    )
    if (desk == "reporting" and (_is_daily_brief_request(normalized) or _is_portfolio_review_request(normalized))) or (
        desk == "research" and _is_strategy_blocker_request(normalized)
    ) or (
        desk == "data" and (_mentions_data_source_gap(normalized) or _is_data_repair_request(normalized))
    ) or (
        desk == "risk" and _mentions_lifecycle(normalized)
    ) or (
        desk == "engineering"
        and (
            _mentions_test_design(normalized)
            or _mentions_ast_diagnostics(normalized)
            or _is_engineering_code_request(normalized)
            or any(token in normalized for token in ("docs", "doc", "文档", "stale"))
        )
    ) or (
        desk == "execution"
        and (
            _mentions_execution_dry_run(normalized)
            or any(token in normalized for token in ("paper", "live", "order", "下单", "执行", "交易"))
        )
    ):
        evidence_summary = _artifact_evidence_summary(artifact_context or {})
        if evidence_summary:
            answer = f"{answer} 当前证据摘要：{'；'.join(evidence_summary[:5])}。"
            reasoning.append(
                _artifact_context_reasoning(
                    artifact_context=artifact_context or {},
                    root_causes=_artifact_root_causes(artifact_context or {}),
                    evidence_summary=evidence_summary,
                )
            )
    return DeskWorkflowPlan(
        desk=desk,
        answer=answer,
        confidence=_confidence_for(desk),
        actions=actions,
        planning_mode=planning_mode,
        reasoning=reasoning,
        handoffs=handoffs,
        work_orders=work_orders,
    )


def _conversation_plan(*, desk: str, content: str) -> DeskWorkflowPlan | None:
    normalized = content.lower().strip()
    if desk != "reporting" or not _is_general_conversation(normalized):
        return None
    return DeskWorkflowPlan(
        desk="reporting",
        answer=(
            "你好，我在。你可以直接描述要处理的数据、策略、组合、风险、交易或工程问题；"
            "CEO Office 会自动分配给对应部门，并把证据引用和需要你审批的行动挂在对话里。"
        ),
        confidence=0.7,
        actions=[],
        planning_mode="conversation",
        reasoning=[
            {
                "kind": "conversation",
                "intent": "greeting_or_help",
                "tool_count": 0,
                "writes_blocked_by_policy": False,
            }
        ],
    )


def _adaptive_artifact_plan(
    *,
    desk: str,
    content: str,
    artifact_context: dict[str, Any],
    session_context: dict[str, Any],
) -> DeskWorkflowPlan | None:
    normalized = content.lower()
    if desk != "reporting":
        return None
    if not _is_session_follow_up_request(normalized) or not _is_artifact_priority_request(normalized):
        return None

    active_actions = [row for row in session_context.get("active_actions", []) if isinstance(row, dict)]
    open_handoffs = [row for row in session_context.get("open_handoffs", []) if isinstance(row, dict)]
    open_work_orders = [row for row in session_context.get("open_work_orders", []) if isinstance(row, dict)]
    if not active_actions and not open_handoffs and not open_work_orders:
        return None

    root_causes = _artifact_root_causes(artifact_context)
    if not root_causes:
        return None

    session_actions = _adaptive_actions_for_session(active_actions, open_handoffs, open_work_orders)
    artifact_actions = _artifact_actions_for_causes(root_causes)
    actions = _dedupe_actions([*session_actions, *artifact_actions])
    if len(actions) < 2:
        return None

    target_desks = _ordered_unique([action.desk for action in actions])
    handoffs = [
        {
            "target_desk": target_desk,
            "reason": f"Adaptive artifact plan needs {target_desk.title()} Desk evidence and backlog follow-up.",
        }
        for target_desk in target_desks
        if target_desk != desk
    ]
    reasoning = _reasoning_for_plan(
        source_desk=desk,
        planning_mode="adaptive_artifact",
        actions=actions,
        handoffs=handoffs,
        work_orders=[],
    )
    reasoning.append(
        _session_backlog_reasoning(
            active_actions=active_actions,
            open_handoffs=open_handoffs,
            open_work_orders=open_work_orders,
        )
    )
    evidence_summary = _artifact_evidence_summary(artifact_context)
    reasoning.append(
        _artifact_context_reasoning(
            artifact_context=artifact_context,
            root_causes=root_causes,
            evidence_summary=evidence_summary,
        )
    )
    reasoning.append(
        {
            "kind": "context_fusion",
            "source_count": 2,
            "sources": ["session_backlog", "artifact_context"],
            "session_action_count": len(session_actions),
            "artifact_action_count": len(artifact_actions),
            "deduped_action_count": len(actions),
        }
    )
    return DeskWorkflowPlan(
        desk=desk,
        answer=(
            "Reporting Desk 已生成 adaptive artifact / 会话与证据融合计划："
            f"当前证据摘要：{'；'.join(evidence_summary[:5])}。"
            "先处理当前 session 未完成事项，再补齐本地 artifact 暴露的数据、策略、风险和工程证据缺口。"
        ),
        confidence=0.82,
        actions=actions,
        planning_mode="adaptive_artifact",
        reasoning=reasoning,
        handoffs=handoffs,
    )


def _adaptive_session_plan(
    *,
    desk: str,
    content: str,
    session_context: dict[str, Any],
) -> DeskWorkflowPlan | None:
    normalized = content.lower()
    if desk != "reporting" or not _is_session_follow_up_request(normalized):
        return None

    active_actions = [row for row in session_context.get("active_actions", []) if isinstance(row, dict)]
    open_handoffs = [row for row in session_context.get("open_handoffs", []) if isinstance(row, dict)]
    open_work_orders = [row for row in session_context.get("open_work_orders", []) if isinstance(row, dict)]
    if not active_actions and not open_handoffs and not open_work_orders:
        return None

    actions = _adaptive_actions_for_session(active_actions, open_handoffs, open_work_orders)
    if not actions:
        return None

    target_desks = _ordered_unique([action.desk for action in actions])
    handoffs = [
        {
            "target_desk": target_desk,
            "reason": f"Adaptive session follow-up needs {target_desk.title()} Desk to close existing open work.",
        }
        for target_desk in target_desks
        if target_desk != desk
    ]
    reasoning = _reasoning_for_plan(
        source_desk=desk,
        planning_mode="adaptive_session",
        actions=actions,
        handoffs=handoffs,
        work_orders=[],
    )
    reasoning.append(
        _session_backlog_reasoning(
            active_actions=active_actions,
            open_handoffs=open_handoffs,
            open_work_orders=open_work_orders,
        )
    )
    return DeskWorkflowPlan(
        desk=desk,
        answer=(
            "Reporting Desk 已根据当前 session 未完成事项生成 adaptive session plan："
            "先复核待审批动作、跟进 open handoff 和工程工单，再把安全证据汇总给 CEO。"
        ),
        confidence=0.76,
        actions=actions,
        planning_mode="adaptive_session",
        reasoning=reasoning,
        handoffs=handoffs,
    )


def _adaptive_actions_for_session(
    active_actions: list[dict[str, Any]],
    open_handoffs: list[dict[str, Any]],
    open_work_orders: list[dict[str, Any]],
) -> list[WorkflowActionSpec]:
    actions: list[WorkflowActionSpec] = []
    for action in active_actions[:8]:
        action_type = str(action.get("action_type") or "")
        risk_level = str(action.get("risk_level") or "")
        params = action.get("parameters") if isinstance(action.get("parameters"), dict) else {}
        tool_id = str(params.get("tool_id") or "")
        if action_type == "data_repair" or tool_id == "astroq.data.repair":
            table = str(params.get("table") or "").strip()
            actions.append(_data_repair_recheck_action(table))
        elif risk_level in {"paper_order", "live_order"} or action_type in {"paper_order", "live_order"}:
            actions.append(_execution_followup_action())
        elif risk_level == "code_change" or action_type == "engineering_work_order":
            actions.extend(_engineering_followup_actions())
        elif str(action.get("desk") or "") == "risk":
            actions.append(_risk_followup_action())

    for handoff in open_handoffs[:8]:
        actions.extend(_handoff_followup_actions(str(handoff.get("target_desk") or "")))

    if open_work_orders:
        actions.extend(_engineering_followup_actions())

    return _dedupe_actions(actions)


def _data_repair_recheck_action(table: str) -> WorkflowActionSpec:
    if _valid_table_name(table):
        return WorkflowActionSpec(
            desk="data",
            action_type="data_repair_dry_run",
            tool_id="astroq.data.repair.dry_run",
            risk_level="dry_run",
            summary=f"Re-check pending Data Desk repair for {table} before CEO approval.",
            expected_effect="Runs a non-writing repair preview so the CEO can decide whether the existing write action is still valid.",
            parameters={"table": table},
            evidence=WorkflowEvidenceSpec(
                label="Data repair dry-run",
                uri="/datahub",
                summary="Open DataHub health and repair preview context.",
            ),
        )
    return _data_status_followup_action()


def _handoff_followup_actions(target_desk: str) -> list[WorkflowActionSpec]:
    if target_desk == "data":
        return [_data_status_followup_action()]
    if target_desk == "research":
        return [_strategy_followup_action()]
    if target_desk == "portfolio":
        return [_portfolio_followup_action()]
    if target_desk == "risk":
        return [_risk_followup_action()]
    if target_desk == "execution":
        return [_execution_followup_action()]
    if target_desk == "engineering":
        return _engineering_followup_actions()
    return []


def _data_status_followup_action() -> WorkflowActionSpec:
    return WorkflowActionSpec(
        desk="data",
        action_type="data_status",
        tool_id="astroq.data.status",
        risk_level="read_only",
        summary="Refresh Data Desk status for open session follow-up.",
        expected_effect="Records current data health without writing data.",
        evidence=WorkflowEvidenceSpec(
            label="DataHub status view",
            uri="/datahub",
            summary="Open DataHub health and source capability details.",
        ),
    )


def _strategy_followup_action() -> WorkflowActionSpec:
    return WorkflowActionSpec(
        desk="research",
        action_type="strategy_competition",
        tool_id="astroq.strategy.compete",
        risk_level="read_only",
        summary="Refresh Research Desk strategy evidence for open session follow-up.",
        expected_effect="Records OOS, IC/ICIR, sample-size, and strategy blocker evidence.",
        evidence=WorkflowEvidenceSpec(
            label="Strategy competition evidence",
            uri="/strategy-lab",
            summary="Open strategy competition and promotion evidence views.",
        ),
    )


def _portfolio_followup_action() -> WorkflowActionSpec:
    return WorkflowActionSpec(
        desk="portfolio",
        action_type="portfolio_decision_review",
        tool_id="astroq.strategy.compete",
        risk_level="read_only",
        summary="Refresh Portfolio Desk decision evidence for open session follow-up.",
        expected_effect="Records strategy, alpha, and blocker evidence for portfolio review without creating target weights or orders.",
        evidence=WorkflowEvidenceSpec(
            label="Portfolio decision workspace",
            uri="/portfolio",
            summary="Open portfolio, strategy evidence, risk gates, and execution readiness.",
        ),
    )


def _risk_followup_action() -> WorkflowActionSpec:
    return WorkflowActionSpec(
        desk="risk",
        action_type="lifecycle_check",
        tool_id="astroq.lifecycle.check",
        risk_level="read_only",
        summary="Refresh lifecycle gates for open session follow-up.",
        expected_effect="Records lifecycle readiness and blocker evidence without changing system state.",
        evidence=WorkflowEvidenceSpec(
            label="Lifecycle readiness",
            uri="/system?tab=lifecycle",
            summary="Open lifecycle readiness and blocker details.",
        ),
    )


def _execution_followup_action() -> WorkflowActionSpec:
    return WorkflowActionSpec(
        desk="execution",
        action_type="execution_dry_run",
        tool_id="astroq.execution.dry_run",
        risk_level="dry_run",
        summary="Refresh execution dry-run readiness for open session follow-up.",
        expected_effect="Produces execution readiness preview without submitting paper or live orders.",
        evidence=WorkflowEvidenceSpec(
            label="Execution readiness",
            uri="/portfolio",
            summary="Open portfolio and execution readiness views.",
        ),
    )


def _engineering_followup_actions() -> list[WorkflowActionSpec]:
    return [
        WorkflowActionSpec(
            desk="engineering",
            action_type="architecture_ast",
            tool_id="astroq.architecture.ast",
            risk_level="read_only",
            summary="Refresh AST diagnostics for open Engineering Desk work.",
            expected_effect="Records duplicate implementation and architecture risk evidence without editing source files.",
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
            summary="Refresh test design diagnostics for open Engineering Desk work.",
            expected_effect="Records test design risk evidence without changing source files.",
            evidence=WorkflowEvidenceSpec(
                label="Test design intelligence",
                uri="/system?tab=tests",
                summary="Open test design intelligence diagnostics.",
            ),
        ),
    ]


def _artifact_aware_plan(
    *,
    desk: str,
    content: str,
    artifact_context: dict[str, Any],
) -> DeskWorkflowPlan | None:
    if desk != "reporting" or not _is_artifact_priority_request(content.lower()):
        return None
    root_causes = _artifact_root_causes(artifact_context)
    if not root_causes:
        return None
    actions = _artifact_actions_for_causes(root_causes)
    if len(actions) < 2:
        return None

    target_desks = _ordered_unique([action.desk for action in actions])
    handoffs = [
        {
            "target_desk": target_desk,
            "reason": f"Artifact-aware CEO priority plan needs {target_desk.title()} Desk evidence.",
        }
        for target_desk in target_desks
    ]
    reasoning = _reasoning_for_plan(
        source_desk=desk,
        planning_mode="artifact_aware",
        actions=actions,
        handoffs=handoffs,
        work_orders=[],
    )
    evidence_summary = _artifact_evidence_summary(artifact_context)
    reasoning.append(
        _artifact_context_reasoning(
            artifact_context=artifact_context,
            root_causes=root_causes,
            evidence_summary=evidence_summary,
        )
    )
    summary_text = "；".join(evidence_summary[:5])
    return DeskWorkflowPlan(
        desk=desk,
        answer=(
            "Reporting Desk 已根据当前本地 artifact evidence 生成 artifact-aware / 证据感知优先级计划："
            f"当前证据摘要：{summary_text}。"
            "先处理数据源、生命周期、策略证据和工程质量链路，再汇总给 CEO。"
        ),
        confidence=0.78,
        actions=actions,
        planning_mode="artifact_aware",
        reasoning=reasoning,
        handoffs=handoffs,
    )


def _artifact_actions_for_causes(root_causes: list[str]) -> list[WorkflowActionSpec]:
    actions: list[WorkflowActionSpec] = []
    cause_set = set(root_causes)
    if "data_source_gap" in cause_set:
        actions.append(
            WorkflowActionSpec(
                desk="data",
                action_type="data_sources_diff",
                tool_id="astroq.data.sources.diff_registry",
                risk_level="read_only",
                summary="Review source capability gaps surfaced by local report artifacts.",
                expected_effect="Records capability-vs-registry gaps without downloading data.",
                evidence=WorkflowEvidenceSpec(
                    label="Data source capability matrix",
                    uri="/datahub?tab=sources",
                    summary="Open data source capability matrix and registry diff.",
                ),
            )
        )
    if "lifecycle_blocker" in cause_set:
        actions.append(
            WorkflowActionSpec(
                desk="risk",
                action_type="lifecycle_check",
                tool_id="astroq.lifecycle.check",
                risk_level="read_only",
                summary="Review lifecycle blockers surfaced by local report artifacts.",
                expected_effect="Records lifecycle readiness and blocker evidence without changing system state.",
                evidence=WorkflowEvidenceSpec(
                    label="Lifecycle readiness",
                    uri="/system?tab=lifecycle",
                    summary="Open lifecycle readiness and blocker details.",
                ),
            )
        )
    if "strategy_evidence_blocked" in cause_set:
        actions.append(
            WorkflowActionSpec(
                desk="research",
                action_type="strategy_competition",
                tool_id="astroq.strategy.compete",
                risk_level="read_only",
                summary="Review blocked strategy evidence surfaced by local report artifacts.",
                expected_effect="Records OOS, IC/ICIR, sample-size, and strategy blocker evidence.",
                evidence=WorkflowEvidenceSpec(
                    label="Strategy competition evidence",
                    uri="/strategy-lab",
                    summary="Open strategy competition and promotion evidence views.",
                ),
            )
        )
        actions.append(_portfolio_followup_action())
    if "engineering_quality_risk" in cause_set:
        actions.append(
            WorkflowActionSpec(
                desk="engineering",
                action_type="architecture_ast",
                tool_id="astroq.architecture.ast",
                risk_level="read_only",
                summary="Review architecture risks surfaced by local report artifacts.",
                expected_effect="Records duplicate implementation and architecture risk evidence without editing source files.",
                evidence=WorkflowEvidenceSpec(
                    label="AST Intelligence",
                    uri="/system?tab=ast",
                    summary="Open AST duplicate implementation diagnostics.",
                ),
            )
        )
    if "test_design_risk" in cause_set:
        actions.append(
            WorkflowActionSpec(
                desk="engineering",
                action_type="test_design",
                tool_id="astroq.test.design",
                risk_level="read_only",
                summary="Review test design risks surfaced by local report artifacts.",
                expected_effect="Records test design risk evidence without changing source files.",
                evidence=WorkflowEvidenceSpec(
                    label="Test design intelligence",
                    uri="/system?tab=tests",
                    summary="Open test design intelligence diagnostics.",
                ),
            )
        )
    return _dedupe_actions(actions)


def _dynamic_multi_intent_plan(
    *,
    desk: str,
    content: str,
    artifact_context: dict[str, Any],
) -> DeskWorkflowPlan | None:
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
    reasoning = _reasoning_for_plan(
        source_desk=desk,
        planning_mode="dynamic_multi_intent",
        actions=actions,
        handoffs=handoffs,
        work_orders=[],
    )
    evidence_summary = _artifact_evidence_summary(artifact_context)
    if evidence_summary:
        reasoning.append(
            _artifact_context_reasoning(
                artifact_context=artifact_context,
                root_causes=_artifact_root_causes(artifact_context),
                evidence_summary=evidence_summary,
            )
        )
    summary_suffix = f" 当前证据摘要：{'；'.join(evidence_summary[:5])}。" if evidence_summary else ""
    return DeskWorkflowPlan(
        desk=desk,
        answer=(
            "Reporting Desk 已生成 dynamic multi-intent / 多意图计划：按 Data、Research、Portfolio、"
            "Risk、Execution 和 Engineering 证据链拆分安全动作，再由 CEO Office 汇总结果。"
            f"{summary_suffix}"
        ),
        confidence=0.72,
        actions=actions,
        planning_mode="dynamic_multi_intent",
        reasoning=reasoning,
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


def _open_ended_adaptive_plan(
    *,
    desk: str,
    content: str,
    artifact_context: dict[str, Any],
) -> DeskWorkflowPlan | None:
    normalized = content.lower()
    if desk != "reporting" or not _is_open_ended_company_request(normalized):
        return None

    actions = [
        _data_status_followup_action(),
        _strategy_catalog_action(),
        _portfolio_followup_action(),
        _risk_followup_action(),
        _execution_followup_action(),
        *_engineering_followup_actions(),
    ]
    target_desks = _ordered_unique([action.desk for action in actions])
    handoffs = [
        {
            "target_desk": target_desk,
            "reason": f"Open-ended CEO operating request needs {target_desk.title()} Desk diagnostic evidence.",
        }
        for target_desk in target_desks
    ]
    reasoning = _reasoning_for_plan(
        source_desk=desk,
        planning_mode="open_ended_adaptive",
        actions=actions,
        handoffs=handoffs,
        work_orders=[],
    )
    reasoning.append(
        {
            "kind": "open_goal_decomposition",
            "target_desks": target_desks,
            "diagnostic_only": True,
            "write_or_trade_actions_blocked": True,
        }
    )
    evidence_summary = _artifact_evidence_summary(artifact_context)
    if evidence_summary:
        reasoning.append(
            _artifact_context_reasoning(
                artifact_context=artifact_context,
                root_causes=_artifact_root_causes(artifact_context),
                evidence_summary=evidence_summary,
            )
        )
    summary_suffix = f" 当前证据摘要：{'；'.join(evidence_summary[:5])}。" if evidence_summary else ""
    return DeskWorkflowPlan(
        desk=desk,
        answer=(
            "Reporting Desk 已生成 open-ended adaptive / 开放式公司运营计划："
            "先让 Data、Research、Portfolio、Risk、Execution 和 Engineering Desk 读取各自证据，"
            "只产出诊断和 dry-run，不直接写数据或交易。"
            f"{summary_suffix}"
        ),
        confidence=0.7,
        actions=actions,
        planning_mode="open_ended_adaptive",
        reasoning=reasoning,
        blockers=["open_ended_plan_is_diagnostic_only"],
        handoffs=handoffs,
    )


def _strategy_catalog_action() -> WorkflowActionSpec:
    return WorkflowActionSpec(
        desk="research",
        action_type="strategy_catalog",
        tool_id="astroq.strategy.catalog",
        risk_level="read_only",
        summary="Read Research Desk strategy catalog for open-ended CEO planning.",
        expected_effect="Records strategy layer and promotion status without running backtests.",
        evidence=WorkflowEvidenceSpec(
            label="Strategy Lab",
            uri="/strategy-lab",
            summary="Open strategy catalog and evidence views.",
        ),
    )


_SEMANTIC_EVIDENCE_BY_TOOL: dict[str, WorkflowEvidenceSpec] = {
    "astroq.health": WorkflowEvidenceSpec(
        label="Project health",
        uri="/system",
        summary="Open system health and runtime status.",
    ),
    "astroq.lifecycle.check": WorkflowEvidenceSpec(
        label="Lifecycle readiness",
        uri="/system?tab=lifecycle",
        summary="Open lifecycle readiness and blocker details.",
    ),
    "astroq.execution.dry_run": WorkflowEvidenceSpec(
        label="Execution readiness",
        uri="/portfolio",
        summary="Open portfolio and execution readiness views.",
    ),
    "astroq.agent.live.readiness": WorkflowEvidenceSpec(
        label="MiniQMT/QMT live readiness",
        uri="/portfolio",
        summary="Open broker readiness, live execution, and kill switch context.",
    ),
    "astroq.architecture.ast": WorkflowEvidenceSpec(
        label="AST Intelligence",
        uri="/system?tab=ast",
        summary="Open AST duplicate implementation diagnostics.",
    ),
    "astroq.test.design": WorkflowEvidenceSpec(
        label="Test design intelligence",
        uri="/system?tab=tests",
        summary="Open test design intelligence diagnostics.",
    ),
    "astroq.docs.check": WorkflowEvidenceSpec(
        label="Documentation hygiene",
        uri="/system?tab=tests",
        summary="Open documentation hygiene evidence.",
    ),
    "astroq.data.status": WorkflowEvidenceSpec(
        label="DataHub status view",
        uri="/datahub",
        summary="Open DataHub health and source capability details.",
    ),
    "astroq.data.sources": WorkflowEvidenceSpec(
        label="Data source capabilities",
        uri="/datahub?tab=sources",
        summary="Open data source capability matrix.",
    ),
    "astroq.data.sources.diff_registry": WorkflowEvidenceSpec(
        label="Data source capability matrix",
        uri="/datahub?tab=sources",
        summary="Open data source capability matrix and registry diff.",
    ),
    "astroq.strategy.catalog": WorkflowEvidenceSpec(
        label="Strategy Lab",
        uri="/strategy-lab",
        summary="Open strategy catalog and evidence views.",
    ),
    "astroq.strategy.compete": WorkflowEvidenceSpec(
        label="Strategy competition evidence",
        uri="/strategy-lab",
        summary="Open strategy competition and promotion evidence views.",
    ),
    "astroq.backtest.run.dry_run": WorkflowEvidenceSpec(
        label="Backtest evidence",
        uri="/research",
        summary="Open research and backtest evidence views.",
    ),
    "astroq.agent.report.daily": WorkflowEvidenceSpec(
        label="CEO report artifacts",
        uri="/",
        summary="Open CEO Office report cards and artifact evidence.",
    ),
    "astroq.data.repair.dry_run": WorkflowEvidenceSpec(
        label="Data repair dry-run",
        uri="/datahub",
        summary="Open DataHub health and repair preview context.",
    ),
}


def _semantic_assisted_plan(
    *,
    desk: str,
    content: str,
    artifact_context: dict[str, Any],
    session_context: dict[str, Any],
    semantic_planner: Any | None,
) -> DeskWorkflowPlan | None:
    if semantic_planner is None:
        return None

    plan_method = getattr(semantic_planner, "plan", None)
    if not callable(plan_method):
        return None

    draft = plan_method(
        desk=desk,
        content=content,
        artifact_context=dict(artifact_context),
        session_context=dict(session_context),
    )
    normalized = _normalize_semantic_draft(draft)
    actions, rejected = _safe_semantic_actions(normalized.actions)
    provider_unavailable = {
        "semantic_context_overflow",
        "semantic_provider_not_configured",
        "semantic_provider_disabled",
        "semantic_provider_unsupported_protocol",
        "semantic_provider_missing_secret",
        "semantic_provider_base_url_missing",
        "semantic_provider_model_missing",
        "semantic_provider_error",
    }
    if (
        getattr(semantic_planner, "fallback_to_deterministic", False)
        and not actions
        and normalized.blockers
        and all(blocker in provider_unavailable for blocker in normalized.blockers)
    ):
        return None
    has_semantic_state = bool(normalized.answer.strip() or normalized.blockers or normalized.reasoning or rejected)
    if not actions and not has_semantic_state:
        return None

    target_desks = _ordered_unique([action.desk for action in actions])
    handoffs = [
        {
            "target_desk": target_desk,
            "reason": f"Semantic-assisted CEO plan needs {target_desk.title()} Desk safe evidence.",
        }
        for target_desk in target_desks
        if target_desk != desk
    ]
    reasoning = _reasoning_for_plan(
        source_desk=desk,
        planning_mode="semantic_assisted",
        actions=actions,
        handoffs=handoffs,
        work_orders=[],
    )
    reasoning.append(
        {
            "kind": "semantic_planner",
            "mode": "opt_in",
            "accepted_action_count": len(actions),
            "rejected_action_count": len(rejected),
            "accepted_tool_ids": [action.tool_id for action in actions],
            "rejected": rejected,
            "manual_review_required": bool(actions or rejected),
        }
    )
    reasoning.extend(dict(row) for row in normalized.reasoning if isinstance(row, dict))
    manual_review_required = bool(actions or rejected)
    blockers = _ordered_unique(
        [
            *[str(blocker) for blocker in normalized.blockers if str(blocker).strip()],
            *(["semantic_plan_requires_manual_review"] if manual_review_required else []),
            *(["unsafe_semantic_actions_filtered"] if rejected else []),
        ]
    )
    return DeskWorkflowPlan(
        desk=desk,
        answer=normalized.answer or "Semantic planner proposed a safe diagnostic plan for CEO review.",
        confidence=max(0.0, min(float(normalized.confidence), 0.95)),
        actions=actions,
        planning_mode="semantic_assisted",
        reasoning=reasoning,
        blockers=blockers,
        handoffs=handoffs,
    )


def _normalize_semantic_draft(value: Any) -> SemanticWorkflowDraft:
    if isinstance(value, SemanticWorkflowDraft):
        confidence, confidence_blockers = _semantic_confidence(value.confidence)
        return SemanticWorkflowDraft(
            answer=str(value.answer or ""),
            confidence=confidence,
            actions=_semantic_dict_rows(value.actions),
            reasoning=_semantic_dict_rows(value.reasoning),
            blockers=_ordered_unique([*_semantic_string_rows(value.blockers), *confidence_blockers]),
        )
    if isinstance(value, dict):
        confidence, confidence_blockers = _semantic_confidence(value.get("confidence"))
        return SemanticWorkflowDraft(
            answer=str(value.get("answer") or ""),
            confidence=confidence,
            actions=_semantic_dict_rows(value.get("actions")),
            reasoning=_semantic_dict_rows(value.get("reasoning")),
            blockers=_ordered_unique([*_semantic_string_rows(value.get("blockers")), *confidence_blockers]),
        )
    return SemanticWorkflowDraft(answer="", confidence=0.5, actions=[])


def _semantic_confidence(value: Any) -> tuple[float, list[str]]:
    if value in (None, ""):
        return 0.5, []
    try:
        return float(value), []
    except (TypeError, ValueError):
        return 0.5, ["semantic_draft_invalid_confidence"]


def _semantic_dict_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [dict(value)]
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _semantic_string_rows(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(row).strip() for row in value if str(row).strip()]
    return [str(value).strip()] if value is not None and str(value).strip() else []


def _safe_semantic_actions(rows: list[dict[str, Any]]) -> tuple[list[WorkflowActionSpec], list[dict[str, str]]]:
    actions: list[WorkflowActionSpec] = []
    rejected: list[dict[str, str]] = []
    for row in rows[:12]:
        tool_id = str(row.get("tool_id") or "").strip()
        requested_desk = str(row.get("desk") or "").strip()
        descriptor = DEFAULT_TOOLS.get(tool_id)
        if descriptor is None:
            rejected.append({"tool_id": tool_id, "desk": requested_desk, "reason": "unknown_tool"})
            continue
        if descriptor.risk_level not in {"read_only", "dry_run"}:
            rejected.append({"tool_id": tool_id, "desk": requested_desk, "reason": "unsafe_risk_level"})
            continue
        if not requested_desk:
            inferred_desk = _infer_single_scope_desk(descriptor.desk_scopes)
            if inferred_desk is None:
                rejected.append({"tool_id": tool_id, "desk": requested_desk, "reason": "missing_or_ambiguous_desk"})
                continue
            requested_desk = inferred_desk
        if requested_desk not in descriptor.desk_scopes:
            rejected.append({"tool_id": tool_id, "desk": requested_desk, "reason": "desk_scope_mismatch"})
            continue
        parameters, parameter_error = _semantic_action_parameters(row.get("parameters"), descriptor.parameter_patterns)
        if parameter_error:
            rejected.append({"tool_id": tool_id, "desk": requested_desk, "reason": parameter_error})
            continue
        evidence = _SEMANTIC_EVIDENCE_BY_TOOL.get(
            tool_id,
            WorkflowEvidenceSpec(
                label=descriptor.label,
                uri="/system",
                summary="Open system evidence for semantic-assisted plan.",
            ),
        )
        actions.append(
            WorkflowActionSpec(
                desk=requested_desk,
                action_type=_semantic_action_type(tool_id),
                tool_id=tool_id,
                risk_level=descriptor.risk_level,
                summary=str(row.get("summary") or descriptor.label).strip() or descriptor.label,
                expected_effect=str(row.get("expected_effect") or "").strip()
                or "Runs a semantic-planner selected safe diagnostic tool without writes or trading.",
                evidence=evidence,
                parameters=parameters,
            )
        )
    return _dedupe_actions(actions), rejected


def _infer_single_scope_desk(desk_scopes: list[str]) -> str | None:
    unique_scopes = _ordered_unique([scope for scope in desk_scopes if scope])
    if len(unique_scopes) == 1:
        return unique_scopes[0]
    return None


def _semantic_action_parameters(value: Any, parameter_patterns: dict[str, str]) -> tuple[dict[str, Any], str]:
    if not parameter_patterns:
        return {}, ""
    if not isinstance(value, dict):
        value = {}
    parameters: dict[str, Any] = {}
    for name, pattern in parameter_patterns.items():
        raw_value = str(value.get(name) or "").strip()
        if not raw_value:
            return {}, f"missing_tool_parameter:{name}"
        if not pattern or not re.fullmatch(pattern, raw_value):
            return {}, f"invalid_tool_parameter:{name}"
        parameters[name] = raw_value
    return parameters, ""


def _semantic_action_type(tool_id: str) -> str:
    return tool_id.removeprefix("astroq.").replace(".", "_").replace("-", "_")


def _profile_for(desk: str, content: str) -> dict[str, str] | None:
    normalized = content.lower()
    for triggers, profile in _INTENT_PROFILES.get(desk, []):
        if any(trigger in normalized for trigger in triggers):
            return profile
    return _DESK_PROFILES.get(desk)


def _confidence_for(desk: str) -> float:
    return 0.68 if desk == "reporting" else 0.64


def _actions_for_profile(
    *,
    desk: str,
    profile: dict[str, str],
    normalized_content: str,
    session_context: dict[str, Any],
) -> list[WorkflowActionSpec]:
    if desk == "reporting" and profile.get("action_type") == "agent_report_daily":
        session_id = str(session_context.get("session_id") or "").strip()
        if not session_id:
            return []
        return [
            WorkflowActionSpec(
                desk="reporting",
                action_type="agent_report_daily",
                tool_id="astroq.agent.report.daily",
                risk_level="write_artifact",
                summary="Generate a daily CEO brief report artifact after CEO approval.",
                expected_effect="Writes a local evidence-cited CEO report artifact only after explicit approval.",
                parameters={"session_id": session_id},
                evidence=WorkflowEvidenceSpec(
                    label="CEO report artifacts",
                    uri="/",
                    summary="Open CEO Office report cards and artifact evidence.",
                ),
            )
        ]
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
                desk="portfolio",
                action_type="portfolio_decision_review",
                tool_id="astroq.strategy.compete",
                risk_level="read_only",
                summary="Read Portfolio Desk decision evidence for portfolio review.",
                expected_effect="Records strategy mix, position sizing, rebalance cadence, and allocation blockers without creating target weights or orders.",
                evidence=WorkflowEvidenceSpec(
                    label="Portfolio decision workspace",
                    uri="/portfolio",
                    summary="Open portfolio, strategy evidence, risk gates, and execution readiness.",
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
            {"target_desk": "portfolio", "reason": "Portfolio review needs position-sizing, rebalance, and strategy-mix decision evidence."},
            {"target_desk": "risk", "reason": "Portfolio review needs lifecycle and risk gate interpretation."},
            {"target_desk": "execution", "reason": "Portfolio review needs execution dry-run readiness."},
        ]
    if desk == "portfolio":
        return [
            {"target_desk": "research", "reason": "Portfolio decisions depend on current strategy, alpha, and research evidence."},
            {"target_desk": "risk", "reason": "Portfolio decisions require risk-gate interpretation before execution."},
            {"target_desk": "execution", "reason": "Portfolio decisions need execution dry-run readiness before orders."},
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


def _is_general_conversation(normalized: str) -> bool:
    text = normalized.strip()
    if not text:
        return False
    greeting_tokens = ("hello", "hi", "你好", "在吗", "帮助", "help", "你能做什么")
    domain_tokens = (
        "数据",
        "策略",
        "组合",
        "仓位",
        "风险",
        "下单",
        "订单",
        "交易",
        "bug",
        "报错",
        "代码",
        "前端",
        "页面",
        "测试",
        "文档",
        "回测",
    )
    return any(token in text for token in greeting_tokens) and not any(token in text for token in domain_tokens)


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


def _is_artifact_priority_request(normalized: str) -> bool:
    broad_tokens = ("今天", "today", "what should", "应该", "先处理", "优先", "priority", "prioritize", "安排")
    evidence_tokens = ("证据", "artifact", "artifacts", "当前", "公司", "desk", "全局", "system")
    report_tokens = ("简报", "brief", "报告", "report")
    return (
        any(token in normalized for token in broad_tokens)
        and any(token in normalized for token in evidence_tokens)
        and not any(token in normalized for token in report_tokens)
    )


def _is_open_ended_company_request(normalized: str) -> bool:
    company_tokens = ("公司", "company", "ceo", "desk", "整体", "全局", "operating", "推进")
    goal_tokens = ("推进", "安排", "判断", "看一下", "检查", "review", "诊断", "plan", "规划")
    forbidden_specific = ("简报", "brief", "portfolio", "组合", "补", "repair", "backfill", "下单", "submit")
    return (
        any(token in normalized for token in company_tokens)
        and any(token in normalized for token in goal_tokens)
        and not any(token in normalized for token in forbidden_specific)
    )


def _is_session_follow_up_request(normalized: str) -> bool:
    tokens = (
        "继续",
        "下一步",
        "未完成",
        "待处理",
        "推进",
        "跟进",
        "open work",
        "follow up",
        "next step",
        "what next",
        "pending",
        "backlog",
    )
    return any(token in normalized for token in tokens)


def _session_backlog_reasoning(
    *,
    active_actions: list[dict[str, Any]],
    open_handoffs: list[dict[str, Any]],
    open_work_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    approval_required = [
        row for row in active_actions if str(row.get("status") or "") in {"approval_required", "approved"}
    ]
    return {
        "kind": "session_backlog",
        "active_action_count": len(active_actions),
        "approval_required_count": len(approval_required),
        "open_handoff_count": len(open_handoffs),
        "open_work_order_count": len(open_work_orders),
        "action_types": _ordered_unique([str(row.get("action_type") or "") for row in active_actions])[:8],
        "target_desks": _ordered_unique([str(row.get("target_desk") or "") for row in open_handoffs])[:8],
    }


def _artifact_root_causes(artifact_context: dict[str, Any]) -> list[str]:
    synthesis = artifact_context.get("synthesis")
    if not isinstance(synthesis, dict):
        return []
    causes: list[str] = []
    for row in synthesis.get("root_causes", []) or []:
        if not isinstance(row, dict):
            continue
        cause = str(row.get("cause") or "").strip()
        if cause and cause not in causes:
            causes.append(cause)
    return causes


def _artifact_context_reasoning(
    *,
    artifact_context: dict[str, Any],
    root_causes: list[str],
    evidence_summary: list[str] | None = None,
) -> dict[str, Any]:
    synthesis = artifact_context.get("synthesis") if isinstance(artifact_context.get("synthesis"), dict) else {}
    return {
        "kind": "artifact_context",
        "status": str(synthesis.get("status") or "unknown"),
        "available_count": int(artifact_context.get("available_count") or 0),
        "missing_count": int(artifact_context.get("missing_count") or 0),
        "invalid_count": int(artifact_context.get("invalid_count") or 0),
        "root_causes": list(root_causes),
        "evidence_summary": list(evidence_summary or _artifact_evidence_summary(artifact_context)),
    }


def _artifact_evidence_summary(artifact_context: dict[str, Any]) -> list[str]:
    items = [item for item in artifact_context.get("items", []) if isinstance(item, dict)]
    by_key = {str(item.get("key") or ""): item for item in items}
    rows: list[str] = []

    lifecycle = by_key.get("lifecycle")
    if lifecycle:
        for finding in lifecycle.get("findings", []) or []:
            if not isinstance(finding, dict) or str(finding.get("kind") or "") != "blockers":
                continue
            evidence = finding.get("evidence")
            if isinstance(evidence, dict):
                dimension = str(evidence.get("dimension") or evidence.get("table") or "").strip()
                reason = str(evidence.get("reason") or evidence.get("status") or "").strip()
                if dimension or reason:
                    rows.append(" ".join(part for part in ("lifecycle:", dimension, reason) if part))
                    break

    data_sources = by_key.get("data_sources")
    if data_sources:
        summary = data_sources.get("summary") if isinstance(data_sources.get("summary"), dict) else {}
        unmapped = _int_from_mapping(summary, "capability_unmapped_count")
        if unmapped > 0:
            rows.append(f"data: {unmapped} unmapped source capabilities")

    strategy = by_key.get("strategy_competition")
    if strategy:
        summary = strategy.get("summary") if isinstance(strategy.get("summary"), dict) else {}
        total = _int_from_mapping(summary, "total")
        blocked = _int_from_mapping(summary, "blocked")
        if blocked > 0 and total > 0:
            rows.append(f"research: {blocked}/{total} strategies blocked")
        elif blocked > 0:
            rows.append(f"research: {blocked} strategies blocked")

    ast_item = by_key.get("ast_intelligence")
    if ast_item:
        summary = ast_item.get("summary") if isinstance(ast_item.get("summary"), dict) else {}
        issue_count = _int_from_mapping(summary, "issue_count")
        if issue_count > 0:
            severity = summary.get("severity_counts")
            severity_text = ""
            if isinstance(severity, dict):
                severity_rows = [
                    f"{key}={int(value)}"
                    for key, value in sorted(severity.items())
                    if _int_like(value) > 0
                ]
                severity_text = f", {', '.join(severity_rows[:3])}" if severity_rows else ""
            rows.append(f"engineering: {issue_count} AST issue(s){severity_text}")

    test_design = by_key.get("test_design")
    if test_design:
        summary = test_design.get("summary") if isinstance(test_design.get("summary"), dict) else {}
        risk_count = _int_from_mapping(summary, "design_risk_count") + _int_from_mapping(summary, "smell_count")
        if risk_count > 0:
            rows.append(f"testing: {risk_count} test design risk(s)")

    missing_count = _int_like(artifact_context.get("missing_count"))
    invalid_count = _int_like(artifact_context.get("invalid_count"))
    if missing_count or invalid_count:
        rows.append(f"artifacts: {missing_count} missing, {invalid_count} invalid")

    return rows[:8]


def _int_from_mapping(mapping: dict[str, Any], key: str) -> int:
    return _int_like(mapping.get(key))


def _int_like(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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


def _valid_table_name(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", value.strip()))


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
