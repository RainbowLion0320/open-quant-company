from pathlib import Path


FRONTEND_SRC = Path("web/frontend/src")


def read_frontend(path: str) -> str:
    return (FRONTEND_SRC / path).read_text(encoding="utf-8")


def test_router_makes_ceo_office_home_and_moves_market_to_market_route():
    router = read_frontend("router/index.ts")

    assert '{ path: "/", name: "ceo-office", component: () => import("../views/CEOOffice.vue") }' in router
    assert '{ path: "/market", name: "market", component: () => import("../views/Market.vue") }' in router
    assert '{ path: "/", name: "market", component: () => import("../views/Market.vue") }' not in router


def test_app_shell_nav_exposes_ceo_office_and_market_separately():
    app = read_frontend("App.vue")
    zh_nav = read_frontend("i18n/messages/zh-CN/nav.ts")
    en_nav = read_frontend("i18n/messages/en-US/nav.ts")
    zh_app = read_frontend("i18n/messages/zh-CN/app.ts")
    en_app = read_frontend("i18n/messages/en-US/app.ts")
    workspace_css = read_frontend("styles/layout/workspace.css")

    assert 'path: "/", labelKey: "nav.ceoOffice"' in app
    assert 'path: "/market", labelKey: "nav.market"' in app
    assert 'if (route.path.startsWith("/market")) return "/market";' in app
    assert 'ceoOffice: "CEO 办公室"' in zh_nav
    assert 'ceoOffice: "CEO Office"' in en_nav
    assert 'class="statusbar-health"' in app
    assert ":aria-label=\"systemHealthLabel\"" in app
    assert ":title=\"systemLabel\"" not in app
    assert "<strong>{{ systemLabel }}</strong>" not in app
    assert "app.health.normal" in app
    assert "app.health.abnormal" in app
    assert "app.health.unavailable" in app
    assert "app.health.degraded" not in app
    assert 'normal: "系统正常"' in zh_app
    assert 'abnormal: "系统异常"' in zh_app
    assert 'unavailable: "健康数据不可用"' in zh_app
    assert 'normal: "System normal"' in en_app
    assert 'abnormal: "System abnormal"' in en_app
    assert 'unavailable: "Health data unavailable"' in en_app
    assert ".statusbar-health strong" not in workspace_css


def test_ceo_office_view_uses_agent_api_and_i18n():
    view = read_frontend("views/CEOOffice.vue")
    app = read_frontend("App.vue")
    api_client = read_frontend("api/client.ts")
    zh_index = read_frontend("i18n/messages/zh-CN/index.ts")
    en_index = read_frontend("i18n/messages/en-US/index.ts")
    zh_app = read_frontend("i18n/messages/zh-CN/app.ts")
    en_app = read_frontend("i18n/messages/en-US/app.ts")
    zh_ceo = read_frontend("i18n/messages/zh-CN/ceoOffice.ts")
    en_ceo = read_frontend("i18n/messages/en-US/ceoOffice.ts")
    css = read_frontend("styles/views/ceo-office.css")
    workspace_css = read_frontend("styles/layout/workspace.css")

    assert "useI18n" in view
    assert "api.agentSessions" in view
    assert "api.agentDesks" not in view
    assert "api.agentActions" in view
    assert "api.agentCreateSession" in view
    assert "api.agentAddMessage" in view
    assert "api.agentSessionStream" in view
    assert "AbortController" in view
    assert "EventSource" not in view
    assert "streamSse" in api_client
    assert "authHeaders()" in api_client
    assert "closeSessionStream" in view
    assert "onBeforeUnmount(closeSessionStream)" in view
    assert "connectRunStream" in view
    assert "api.agentRunStream" in view
    assert "closeRunStream" in view
    assert "onBeforeUnmount(closeRunStream)" in view

    # CEO Office remains a conversation, decision, and evidence surface.
    assert "deskLabel(message.desk)" in view
    assert "selectedDraftDesk" not in view
    assert 'v-model="selectedDraftDesk"' not in view
    assert 'v-for="desk in desks"' not in view
    assert "desk: selectedDraftDesk.value" not in view
    assert "ceoOffice.messageDesk" not in view
    assert "selectedAction" in view
    assert "api.agentAction" in view
    assert "api.agentModelRuntime" not in view
    assert "api.agentModelRuntime" in app
    assert "api.agentApproveAction" in view
    assert "api.agentRejectAction" in view
    assert "api.agentPaperSubmitAction" in view
    assert "api.agentPaperCancelAction" in view
    assert "api.agentCancelAction" in view
    assert "submitPaperAction" in view
    assert "canSubmitPaperAction" in view
    assert "cancelAction" in view
    assert "selectedEvidence" in view
    assert "selectedEvidenceNavigation" in view
    assert "selectedEvidenceSnapshot" in view
    assert "api.agentEvidence" in view
    assert "message.evidence_refs" in view
    assert "message.action_refs" in view
    assert "actionById" in view
    assert "messageHasSelectedEvidence" in view
    assert "message-action-list" in view
    assert "inline-action-card" in view
    assert "inline-detail" in view
    assert "modelRuntimeSegments" not in view
    assert "agentRuntimeSegments" in app
    assert "formatTokenK" not in view
    assert "formatTokenK" in app
    assert "composer-input-row" in view
    assert "composer-status-line" not in view
    assert "agent-runtime-line" in app
    assert "runtime-segment" in app
    assert "runtime-progress" in app
    assert "runtimeBatteryCells" in app
    assert "agentContextBatteryCells" in app
    assert "context-progress" in app
    assert "contextStatusKind" in app
    assert "runtime-progress-cell" in workspace_css
    assert "runtime-progress::after" not in workspace_css
    assert "runtime-progress-compacted" in workspace_css
    assert "runtime-progress-blocked" in workspace_css
    assert "contextUsedTokens" not in view
    assert "contextUsagePct" not in view
    assert "app.modelRuntimeA11y" in app
    assert "app.reasoningShort" in app
    assert "app.contextShort" in app
    assert "oqc-agent-runtime-session" in view
    assert "handleAgentRuntimeSession" in app
    for reasoning_level in ["max", "xhigh", "high", "mid", "medium", "low"]:
        assert f'level === "{reasoning_level}"' in app
    assert "formatTokenCount(contextUsedTokens" not in view
    assert "formatTokenCount(agentModelRuntime.value.context.max_tokens)" not in app
    assert '{ key: "usage"' not in view
    assert '{ key: "context-status"' not in view
    assert "contextStatusShort" not in app
    assert "formatTokenK(contextUsedTokens.value)" not in view
    assert "ceoOffice.openEvidence" in view
    assert "ceoOffice.viewDetails" in view
    assert "message-action-list" in css
    assert "inline-action-card" in css
    assert "inline-detail" in css
    assert ".composer-input-row" in css
    assert ".composer-status-line" not in css
    assert ".agent-runtime-line" in workspace_css
    assert "overflow: hidden;" in workspace_css
    assert "overflow-x: auto" not in workspace_css
    assert "position: sticky" in css
    assert "bottom: 0" in css
    assert "flex: 1 1 auto" in css
    assert "grid-template-rows: auto minmax(0, 1fr) auto" in css

    # The CEO page must not become a runtime/ops control panel again.
    forbidden_view_tokens = [
        "ceo-side",
        "desk-target-control",
        "actionQueue",
        "attentionActions",
        "attentionStatuses",
        "api.agentApprovalPolicies",
        "api.agentHandoffs",
        "api.agentResolveHandoff",
        "api.agentWorkOrders",
        "api.agentUpdateWorkOrder",
        "api.agentReports",
        "api.agentGenerateReport",
        "api.agentRunReportRhythm",
        "api.agentRunScheduledReportRhythm",
        "api.agentNotifyReport",
        "api.agentLiveReadiness",
        "api.agentLiveEnvironment",
        "api.agentLiveKillSwitch",
        "api.agentLiveKillSwitchActivate",
        "api.agentLiveKillSwitchDeactivate",
        "api.agentLiveReconciliation",
        "api.agentLiveMonitor",
        "approvalPolicies",
        "policyDecisionLabel",
        "handoffs",
        "workOrders",
        "reports",
        "rhythmResult",
        "scheduledRhythmResult",
        "notificationResult",
        "liveReadiness",
        "liveEnvironment",
        "liveKillSwitch",
        "liveReconciliation",
        "liveMonitor",
        "resolveHandoff",
        "updateWorkOrder",
        "generateReport",
        "runReportRhythm",
        "runScheduledReportRhythm",
        "notifyReport",
        "operateLiveKillSwitch",
        "runLiveReconciliation",
        "runLiveMonitor",
        "runAction",
        "api.agentRunAction",
        "selectedDesk",
        "selectedDeskId",
        "deskScopedMessages",
        "deskScopedActions",
        "deskScopedHandoffs",
        "ceoOffice.deskStatus",
        "ceoOffice.approvalPolicies",
        "ceoOffice.workOrders",
        "ceoOffice.handoffs",
        "ceoOffice.liveReadiness",
        "ceoOffice.reports",
        "ceoOffice.runRhythm",
        "ceoOffice.runScheduledRhythm",
        "ceoOffice.runLiveMonitor",
        "ceoOffice.runLiveReconciliation",
        "ceoOffice.generateReport",
        "ceoOffice.notifyReport",
        "ceoOffice.runAction",
    ]
    for token in forbidden_view_tokens:
        assert token not in view

    # Planner/autonomy/debug controls remain hidden from CEO Office.
    forbidden_planner_tokens = [
        "previewWorkflowPlan",
        "workflowPlan",
        "planningWorkflow",
        "semanticDraftEnabled",
        "providerSemanticEnabled",
        "providerPlannerProvider",
        "providerPlannerModel",
        "semanticDraftText",
        "semanticPayload",
        "providerSemanticPayload",
        "api.agentAutonomyStep",
        "runAutonomyStep",
        "api.agentAutonomyRun",
        "runAutonomyRun",
        "api.agentPrograms",
        "api.agentCreateProgram",
        "api.agentRunProgram",
        "agentPrograms",
        "programRunResult",
    ]
    for token in forbidden_planner_tokens:
        assert token not in view

    assert "ceoOffice" in zh_index
    assert "ceoOffice" in en_index
    assert "自动分配主责部门" in zh_ceo
    assert "数据工程部" in zh_ceo
    assert "量化研究部" in zh_ceo
    assert "组合管理部" in zh_ceo
    assert "风险管理部" in zh_ceo
    assert "交易执行部" in zh_ceo
    assert "技术平台部" in zh_ceo
    assert "运营报告部" in zh_ceo
    assert "证据详情" in zh_ceo
    assert "提交纸面订单" in zh_ceo
    assert "纸面订单预览" in zh_ceo
    assert "运行证据" in zh_ceo
    assert "运行时间线" in zh_ceo
    assert "assigns the responsible desk" in en_ceo
    assert "Evidence Detail" in en_ceo
    assert "Submit Paper Order" in en_ceo
    assert "Paper Order Preview" in en_ceo
    assert "Run Evidence" in en_ceo
    assert "Run Timeline" in en_ceo
    assert "modelRuntimeA11y" not in zh_ceo
    assert 'reasoningShort: "R"' in zh_app
    assert 'reasoningMaxShort: "最大"' in zh_app
    assert 'reasoningXHighShort: "极高"' in zh_app
    assert 'reasoningHighShort: "高"' in zh_app
    assert 'reasoningMidShort: "中"' in zh_app
    assert 'reasoningLowShort: "低"' in zh_app
    assert 'contextShort: "CTX"' in zh_app
    assert "modelRuntimeA11y" not in en_ceo
    assert 'reasoningShort: "R"' in en_app
    assert 'reasoningMaxShort: "Max"' in en_app
    assert 'reasoningXHighShort: "XHigh"' in en_app
    assert 'reasoningHighShort: "High"' in en_app
    assert 'reasoningMidShort: "Mid"' in en_app
    assert 'reasoningLowShort: "Low"' in en_app
    assert 'contextShort: "CTX"' in en_app
    assert "已用上下文" not in zh_ceo
    assert "最大上下文" not in zh_ceo
    assert "Context Used" not in en_ceo
    assert "Max Context" not in en_ceo

    forbidden_zh_phrases = [
        "行动队列",
        "行动详情",
        "查看行动",
        "纸面订单对账",
        "Desk 状态",
        "审批策略",
        "交接事项",
        "工程工单",
        "暂无工程工单",
        "影响文件",
        "建议验证",
        "处理工单",
        "取消工单",
        "实盘就绪",
        "实盘红灯",
        "运行实盘监控",
        "运行实盘对账",
        "报告类型",
        "生成报告",
        "运行节奏",
        "运行后台节奏",
        "通知报告",
        "语义草案",
        "Provider 规划",
        "运行自主步骤",
        "自主步骤状态",
    ]
    for phrase in forbidden_zh_phrases:
        assert phrase not in zh_ceo

    forbidden_en_phrases = [
        "Action Queue",
        "Action Detail",
        "View Action",
        "Paper Reconciliation",
        "Desk Status",
        "Approval Policies",
        "Handoffs",
        "Engineering Work Orders",
        "No engineering work orders",
        "Affected Files",
        "Suggested Verification",
        "Start Work",
        "Cancel Work",
        "Live Readiness",
        "Live Kill Switch",
        "Run Live Monitor",
        "Run Live Reconciliation",
        "Report Type",
        "Generate Report",
        "Run Rhythm",
        "Run Scheduled Rhythm",
        "Notify Report",
        "Semantic Draft",
        "Provider Planner",
        "Run Autonomy Step",
        "Autonomy Step Status",
    ]
    for phrase in forbidden_en_phrases:
        assert phrase not in en_ceo

def test_frontend_agent_api_module_exports_runtime_types_and_calls():
    api_index = read_frontend("api/index.ts")
    api_types = read_frontend("api/types.ts")
    agent_api = read_frontend("api/modules/agent.ts")
    agent_types = read_frontend("api/types/agent.ts")

    assert "agentApi" in api_index
    assert 'export * from "./types/agent";' in api_types
    assert "AgentActionFilters" in agent_types
    assert "agentSessions" in agent_api
    assert "agentCreateSession" in agent_api
    assert "agentUpdateSession" in agent_api
    assert "AgentModelRuntimeResponse" in agent_types
    assert "agentModelRuntime" in agent_api
    assert "get<AgentModelRuntimeResponse>" in agent_api
    assert "/api/agent/model-runtime" in agent_api
    assert "agentRunSession" + "ReadOnlyActions" not in agent_api
    assert "run-" + "readonly" not in agent_api
    assert "agentApprovalPolicies" in agent_api
    assert '"/api/agent/policies"' in agent_api
    assert "AgentAddMessageResponse" in agent_api
    assert "AgentWorkflowPlanResponse" in agent_api
    assert "agentPlan" in agent_api
    assert '"/api/agent/plans"' in agent_api
    assert "AgentSessionStreamSnapshot" in agent_types
    assert "agentSessionStream" in agent_api
    assert "streamSse" in agent_api
    assert '`/api/agent/sessions/${encodeURIComponent(sessionId)}/stream`' in agent_api
    assert "AgentRunStreamSnapshot" in agent_types
    assert "agentRunStream" in agent_api
    assert "run_snapshot" in agent_api
    assert '`/api/agent/runs/${encodeURIComponent(runId)}/stream`' in agent_api
    assert "AgentAutonomyStep" in agent_types
    assert "AgentAutonomyStepResponse" in agent_types
    assert "AgentAutonomyRun" in agent_types
    assert "AgentAutonomyRunResponse" in agent_types
    assert "AgentProgram" in agent_types
    assert "AgentProgramRun" in agent_types
    assert "AgentProgramsResponse" in agent_types
    assert "AgentProgramRunResponse" in agent_types
    assert "agentAutonomyStep" in agent_api
    assert "/api/agent/sessions/${encodeURIComponent(sessionId)}/autonomy-step" in agent_api
    assert "agentAutonomyRun" in agent_api
    assert "/api/agent/sessions/${encodeURIComponent(sessionId)}/autonomy-run" in agent_api
    assert "max_steps?: number" in agent_api
    assert "planner_mode?: string" in agent_api
    assert "semantic_draft?: Record<string, unknown>" in agent_api
    assert "planning_mode: string" in agent_types
    assert "agentPrograms" in agent_api
    assert "/api/agent/programs" in agent_api
    assert "agentCreateProgram" in agent_api
    assert "/api/agent/sessions/${encodeURIComponent(sessionId)}/programs" in agent_api
    assert "agentRunProgram" in agent_api
    assert "/api/agent/programs/${encodeURIComponent(programId)}/run" in agent_api
    assert "agentActions" in agent_api
    assert "filters: AgentActionFilters = {}" in agent_api
    assert "URLSearchParams" in agent_api
    assert "session_id" in agent_api
    assert "risk_level" in agent_api
    assert "agentApproveAction" in agent_api
    assert "agentRejectAction" in agent_api
    assert "agentCancelAction" in agent_api
    assert "agentRunAction" in agent_api
    assert "agentPaperSubmitAction" in agent_api
    assert "agentPaperCancelAction" in agent_api
    assert "/api/agent/paper/actions" in agent_api
    assert "agentHandoffs" in agent_api
    assert "agentResolveHandoff" in agent_api
    assert "agentWorkOrders" in agent_api
    assert "agentUpdateWorkOrder" in agent_api
    assert '"/api/agent/work-orders' in agent_api
    assert "/api/agent/work-orders/${encodeURIComponent(workOrderId)}" in agent_api
    assert "agentReports" in agent_api
    assert "agentGenerateReport" in agent_api
    assert "agentRunReportRhythm" in agent_api
    assert "agentRunScheduledReportRhythm" in agent_api
    assert "agentNotifyReport" in agent_api
    assert "/api/agent/reports/rhythm" in agent_api
    assert "/api/agent/reports/rhythm/scheduled" in agent_api
    assert "/api/agent/reports/${encodeURIComponent(reportId)}/notify" in agent_api
    assert "agentLiveReadiness" in agent_api
    assert "agentLiveEnvironment" in agent_api
    assert "agentLiveKillSwitch" in agent_api
    assert "agentLiveKillSwitchActivate" in agent_api
    assert "agentLiveKillSwitchDeactivate" in agent_api
    assert "agentLiveReconciliation" in agent_api
    assert "agentLiveMonitor" in agent_api
    assert "/api/agent/live/environment" in agent_api
    assert "/api/agent/live/kill-switch" in agent_api
    assert "/api/agent/live/reconciliation" in agent_api
    assert "/api/agent/live/monitor" in agent_api
    assert "export interface AgentSession" in agent_types
    assert "export interface AgentReadOnly" + "Workflow" not in agent_types
    assert "export interface AgentReadOnly" + "WorkflowResponse" not in agent_types
    assert "export interface AgentApprovalPolicy" in agent_types
    assert "export interface AgentApprovalPoliciesResponse" in agent_types
    assert "export interface AgentReport" in agent_types
    assert "export interface AgentReportRhythm" in agent_types
    assert "export interface AgentReportRhythmResponse" in agent_types
    assert "export interface AgentScheduledReportRhythm" in agent_types
    assert "export interface AgentScheduledReportRhythmResponse" in agent_types
    assert "export interface AgentReportNotification" in agent_types
    assert "export interface AgentReportNotificationResponse" in agent_types
    assert "export interface AgentLiveReadiness" in agent_types
    assert "export interface AgentLiveEnvironment" in agent_types
    assert "export interface AgentLiveEnvironmentResponse" in agent_types
    assert "export interface AgentLiveKillSwitch" in agent_types
    assert "export interface AgentLiveKillSwitchResponse" in agent_types
    assert "export interface AgentLiveReconciliation" in agent_types
    assert "export interface AgentLiveReconciliationResponse" in agent_types
    assert "export interface AgentLiveMonitor" in agent_types
    assert "export interface AgentLiveMonitorResponse" in agent_types
    assert "live_kill_switch?: AgentLiveKillSwitch" in agent_types
    assert "export interface AgentAction" in agent_types
    assert "export interface AgentRunEvent" in agent_types
    assert "events?: AgentRunEvent[]" in agent_types
    assert "expires_at: string" in agent_types
    assert "export interface AgentActionDetail" in agent_types
    assert "paper_reconciliations: AgentPaperReconciliation[]" in agent_types
    assert "export interface AgentPaperReconciliation" in agent_types
    assert "export interface AgentHandoff" in agent_types
    assert "export interface AgentWorkOrder" in agent_types
    assert "resolution: string" in agent_types
    assert "resolved_at: string | null" in agent_types
    assert "export interface AgentWorkOrderResponse" in agent_types
    assert "export interface AgentWorkOrdersResponse" in agent_types
    assert "work_orders: AgentWorkOrder[]" in agent_types
    assert "export interface AgentDeskResponse" in agent_types
    assert "export interface AgentAddMessageResponse" in agent_types
    assert "export interface AgentPaperSubmitResponse" in agent_types
    assert "export interface AgentPaperCancelResponse" in agent_types
    assert "desk_response?: AgentDeskResponse" in agent_types
    assert "export interface EvidenceRef" in agent_types
    assert "snapshot_uri: string" in agent_types
    assert "export interface AgentEvidenceSnapshot" in agent_types
    assert "snapshot: AgentEvidenceSnapshot | null" in agent_types
    assert "export interface EvidenceNavigation" in agent_types
    assert "navigation: EvidenceNavigation | null" in agent_types
