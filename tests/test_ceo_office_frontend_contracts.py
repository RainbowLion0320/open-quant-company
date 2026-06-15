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

    assert 'path: "/", labelKey: "nav.ceoOffice"' in app
    assert 'path: "/market", labelKey: "nav.market"' in app
    assert 'if (route.path.startsWith("/market")) return "/market";' in app
    assert 'ceoOffice: "CEO 办公室"' in zh_nav
    assert 'ceoOffice: "CEO Office"' in en_nav


def test_ceo_office_view_uses_agent_api_and_i18n():
    view = read_frontend("views/CEOOffice.vue")
    api_client = read_frontend("api/client.ts")
    zh_index = read_frontend("i18n/messages/zh-CN/index.ts")
    en_index = read_frontend("i18n/messages/en-US/index.ts")
    zh_ceo = read_frontend("i18n/messages/zh-CN/ceoOffice.ts")
    en_ceo = read_frontend("i18n/messages/en-US/ceoOffice.ts")

    assert "useI18n" in view
    assert "api.agentSessions" in view
    assert "api.agentDesks" in view
    assert "api.agentApprovalPolicies" in view
    assert "api.agentCreateSession" in view
    assert "api.agentUpdateSession" in view
    assert "api.agentAddMessage" in view
    assert "api.agentPlan" in view
    assert "api.agentSessionStream" in view
    assert "AbortController" in view
    assert "EventSource" not in view
    assert "streamSse" in api_client
    assert "authHeaders()" in api_client
    assert "sessionStreamStatus" in view
    assert "closeSessionStream" in view
    assert "onBeforeUnmount(closeSessionStream)" in view
    assert "runStreamStatus" in view
    assert "connectRunStream" in view
    assert "api.agentRunStream" in view
    assert "closeRunStream" in view
    assert "onBeforeUnmount(closeRunStream)" in view
    assert "previewWorkflowPlan" in view
    assert "workflowPlan" in view
    assert "planningWorkflow" in view
    assert "semanticDraftEnabled" in view
    assert "providerSemanticEnabled" in view
    assert "providerPlannerProvider" in view
    assert "providerPlannerModel" in view
    assert "semanticDraftText" in view
    assert "semanticDraftError" in view
    assert "parseSemanticDraft" in view
    assert "semanticPayload" in view
    assert "providerSemanticPayload" in view
    assert "planner_mode: \"semantic_draft\"" in view
    assert "planner_mode: \"provider_semantic\"" in view
    assert "planner_provider: providerPlannerProvider.value.trim()" in view
    assert "planner_model: providerPlannerModel.value.trim()" in view
    assert "semantic_draft: semanticDraft" in view
    assert 'v-model="semanticDraftEnabled"' in view
    assert 'v-model="providerSemanticEnabled"' in view
    assert 'v-model="providerPlannerProvider"' in view
    assert 'v-model="providerPlannerModel"' in view
    assert 'v-model="semanticDraftText"' in view
    assert "api.agentRunSessionReadOnlyActions" in view
    assert "runSessionReadOnlyActions" in view
    assert "readOnlyWorkflowResult" in view
    assert "runningReadOnlyWorkflow" in view
    assert "api.agentAutonomyStep" in view
    assert "runAutonomyStep" in view
    assert "autonomyStepResult" in view
    assert "runningAutonomyStep" in view
    assert "ceoOffice.runAutonomyStep" in view
    assert "ceoOffice.autonomyStepStatus" in view
    assert "selectedDraftDesk" in view
    assert "selectedDeskId" in view
    assert "selectedDesk" in view
    assert "deskScopedMessages" in view
    assert "deskScopedActions" in view
    assert "deskScopedHandoffs" in view
    assert "selectDesk" in view
    assert 'v-model="selectedDraftDesk"' in view
    assert 'v-for="desk in desks"' in view
    assert "approvalPolicies" in view
    assert "policyDecisionLabel" in view
    assert '@click="selectDesk(desk.desk_id)"' in view
    assert 'selected: selectedDeskId === desk.desk_id' in view
    assert 'desk: selectedDraftDesk.value' in view
    assert "ceoOffice.messageDesk" in view
    assert "ceoOffice.stream" in view
    assert "ceoOffice.previewPlan" in view
    assert "ceoOffice.workflowPlan" in view
    assert "ceoOffice.semanticDraft" in view
    assert "ceoOffice.providerSemantic" in view
    assert "ceoOffice.providerPlannerProvider" in view
    assert "ceoOffice.providerPlannerModel" in view
    assert "ceoOffice.providerPlannerProviderPlaceholder" in view
    assert "ceoOffice.providerPlannerModelPlaceholder" in view
    assert "ceoOffice.providerPlannerNotice" in view
    assert "ceoOffice.semanticDraftPlaceholder" in view
    assert "ceoOffice.semanticDraftInvalid" in view
    assert "ceoOffice.noLedgerWrites" in view
    assert "ceoOffice.runReadOnlyWorkflow" in view
    assert "ceoOffice.readOnlyWorkflowStatus" in view
    assert "ceoOffice.deskMandate" in view
    assert "ceoOffice.allowedTools" in view
    assert "ceoOffice.approvalPolicies" in view
    assert "ceoOffice.defaultDecision" in view
    assert "ceoOffice.requiredRole" in view
    assert "ceoOffice.policyReason" in view
    assert "ceoOffice.forbiddenActions" in view
    assert "ceoOffice.evidenceRequired" in view
    assert "ceoOffice.relatedMessages" in view
    assert "ceoOffice.relatedActions" in view
    assert "ceoOffice.relatedHandoffs" in view
    assert "api.agentAction" in view
    assert "api.agentRunAction" in view
    assert "api.agentPaperSubmitAction" in view
    assert "api.agentPaperCancelAction" in view
    assert "api.agentCancelAction" in view
    assert "selectedAction" in view
    assert "submitPaperAction" in view
    assert "isPaperAction" in view
    assert "canSubmitPaperAction" in view
    assert "paperOrderPreview" in view
    assert "paperReconciliation" in view
    assert "paperReconciliationSummary" in view
    assert "paper_reconciliations" in view
    assert "run.artifact_refs" in view
    assert "ceoOffice.runEvidence" in view
    assert "run.events" in view
    assert "ceoOffice.runTimeline" in view
    assert "event.sequence" in view
    assert "event.event_type" in view
    assert "event.message" in view
    assert "cancelAction" in view
    assert "canCancelAction" in view
    assert "selectedAction.action.expires_at" in view
    assert "ceoOffice.expiresAt" in view
    assert "archiveSession" in view
    assert "archivingSession" in view
    assert "selectedEvidence" in view
    assert "selectedEvidenceNavigation" in view
    assert "selectedEvidenceSnapshot" in view
    assert "selectedEvidenceStatus" in view
    assert "openLinkedView" in view
    assert "handoffs" in view
    assert "api.agentHandoffs" in view
    assert "api.agentResolveHandoff" in view
    assert "api.agentWorkOrders" in view
    assert "workOrders" in view
    assert "ceoOffice.workOrders" in view
    assert "ceoOffice.noWorkOrders" in view
    assert "ceoOffice.affectedFiles" in view
    assert "ceoOffice.suggestedVerification" in view
    assert "resolveHandoff" in view
    assert "api.agentReports" in view
    assert "api.agentGenerateReport" in view
    assert "api.agentRunReportRhythm" in view
    assert "api.agentRunScheduledReportRhythm" in view
    assert "api.agentNotifyReport" in view
    assert "rhythmResult" in view
    assert "scheduledRhythmResult" in view
    assert "notificationResult" in view
    assert "runReportRhythm" in view
    assert "runScheduledReportRhythm" in view
    assert "notifyReport" in view
    assert "runningRhythm" in view
    assert "notifyingReport" in view
    assert "selectedReportKind" in view
    assert "reportKindOptions" in view
    assert "kind: selectedReportKind.value" in view
    assert "api.agentLiveReadiness" in view
    assert "api.agentLiveEnvironment" in view
    assert "api.agentLiveKillSwitch" in view
    assert "api.agentLiveKillSwitchActivate" in view
    assert "api.agentLiveKillSwitchDeactivate" in view
    assert "api.agentLiveReconciliation" in view
    assert "api.agentLiveMonitor" in view
    assert "liveReadiness" in view
    assert "liveEnvironment" in view
    assert "liveEnvironmentChecks" in view
    assert "liveKillSwitch" in view
    assert "liveReconciliation" in view
    assert "liveMonitor" in view
    assert "operateLiveKillSwitch" in view
    assert "runLiveReconciliation" in view
    assert "runLiveMonitor" in view
    assert "runningLiveMonitor" in view
    assert "ceoOffice.liveReadiness" in view
    assert "ceoOffice.liveEnvironment" in view
    assert "ceoOffice.environmentChecks" in view
    assert "ceoOffice.liveKillSwitch" in view
    assert "ceoOffice.activateKillSwitch" in view
    assert "ceoOffice.deactivateKillSwitch" in view
    assert "ceoOffice.runLiveReconciliation" in view
    assert "ceoOffice.liveReconciliation" in view
    assert "ceoOffice.runLiveMonitor" in view
    assert "ceoOffice.liveMonitor" in view
    assert "ceoOffice.liveMonitorFailed" in view
    assert "reports" in view
    assert "reportSectionPreview" in view
    assert "report.sections" in view
    assert "ceoOffice.reportSections" in view
    assert "generateReport" in view
    assert "ceoOffice.reportKind" in view
    assert "ceoOffice.generateReport" in view
    assert "ceoOffice.runRhythm" in view
    assert "ceoOffice.runScheduledRhythm" in view
    assert "ceoOffice.notifyReport" in view
    assert "ceoOffice.notificationStatus" in view
    assert "ceoOffice.sent" in view
    assert "ceoOffice.rhythmStatus" in view
    assert "ceoOffice.sessionCount" in view
    assert "ceoOffice.reports" in view
    assert "报告要点" in zh_ceo
    assert "实盘监控" in zh_ceo
    assert "语义草案" in zh_ceo
    assert "Provider 规划" in zh_ceo
    assert "Provider 名称" in zh_ceo
    assert "模型名称" in zh_ceo
    assert "会调用外部 LLM provider" in zh_ceo
    assert "token/成本记录" in zh_ceo
    assert "运行自主步骤" in zh_ceo
    assert "自主步骤状态" in zh_ceo
    assert "Report Sections" in en_ceo
    assert "Run Live Monitor" in en_ceo
    assert "Semantic Draft" in en_ceo
    assert "Provider Planner" in en_ceo
    assert "Provider Name" in en_ceo
    assert "Model Name" in en_ceo
    assert "Calls the external LLM provider" in en_ceo
    assert "token/cost usage" in en_ceo
    assert "Run Autonomy Step" in en_ceo
    assert "Autonomy Step Status" in en_ceo
    assert "ceoOffice.submitPaperOrder" in view
    assert "ceoOffice.paperOrderPreview" in view
    assert "ceoOffice.paperReconciliation" in view
    assert "ceoOffice.orderId" in view
    assert "ceoOffice.cashAfter" in view
    assert "ceoOffice.marketValueAfter" in view
    assert "ceoOffice.riskGate" in view
    assert "ceoOffice.runEvidence" in view
    assert "ceoOffice" in zh_index
    assert "ceoOffice" in en_index
    assert "行动队列" in zh_ceo
    assert "目标 Desk" in zh_ceo
    assert "实时流" in zh_ceo
    assert "已连接" in zh_ceo
    assert "连接中" in zh_ceo
    assert "预览计划" in zh_ceo
    assert "工作流计划" in zh_ceo
    assert "不会写入 ledger" in zh_ceo
    assert "运行安全工作流" in zh_ceo
    assert "安全工作流状态" in zh_ceo
    assert "Desk 职责" in zh_ceo
    assert "允许工具" in zh_ceo
    assert "审批策略" in zh_ceo
    assert "默认决策" in zh_ceo
    assert "要求角色" in zh_ceo
    assert "策略原因" in zh_ceo
    assert "禁止行动" in zh_ceo
    assert "证据要求" in zh_ceo
    assert "相关消息" in zh_ceo
    assert "相关行动" in zh_ceo
    assert "相关交接" in zh_ceo
    assert "Action Queue" in en_ceo
    assert "Target Desk" in en_ceo
    assert "Stream" in en_ceo
    assert "Connected" in en_ceo
    assert "Connecting" in en_ceo
    assert "Preview Plan" in en_ceo
    assert "Workflow Plan" in en_ceo
    assert "No ledger writes" in en_ceo
    assert "Run Safe Workflow" in en_ceo
    assert "Safe Workflow Status" in en_ceo
    assert "Desk Mandate" in en_ceo
    assert "Allowed Tools" in en_ceo
    assert "Approval Policies" in en_ceo
    assert "Default Decision" in en_ceo
    assert "Required Role" in en_ceo
    assert "Policy Reason" in en_ceo
    assert "Forbidden Actions" in en_ceo
    assert "Evidence Required" in en_ceo
    assert "Related Messages" in en_ceo
    assert "Related Actions" in en_ceo
    assert "Related Handoffs" in en_ceo
    assert "归档会话" in zh_ceo
    assert "Archive Session" in en_ceo
    assert "交接事项" in zh_ceo
    assert "工程工单" in zh_ceo
    assert "暂无工程工单" in zh_ceo
    assert "影响文件" in zh_ceo
    assert "建议验证" in zh_ceo
    assert "更新工单失败" in zh_ceo
    assert "处理工单" in zh_ceo
    assert "取消工单" in zh_ceo
    assert "标记完成" in zh_ceo
    assert "Handoffs" in en_ceo
    assert "Engineering Work Orders" in en_ceo
    assert "No engineering work orders" in en_ceo
    assert "Affected Files" in en_ceo
    assert "Suggested Verification" in en_ceo
    assert "Failed to update work order" in en_ceo
    assert "Start Work" in en_ceo
    assert "Cancel Work" in en_ceo
    assert "Resolve" in en_ceo
    assert "取消行动" in zh_ceo
    assert "已取消" in zh_ceo
    assert "已过期" in zh_ceo
    assert "过期时间" in zh_ceo
    assert "Cancel Action" in en_ceo
    assert "Canceled" in en_ceo
    assert "Expired" in en_ceo
    assert "Expires At" in en_ceo
    assert "证据详情" in zh_ceo
    assert "证据快照" in zh_ceo
    assert "当前哈希" in zh_ceo
    assert "打开关联视图" in zh_ceo
    assert "Evidence Detail" in en_ceo
    assert "Evidence Snapshot" in en_ceo
    assert "Current Hash" in en_ceo
    assert "Open Linked View" in en_ceo
    assert "报告" in zh_ceo
    assert "报告类型" in zh_ceo
    assert "生成报告" in zh_ceo
    assert "CEO 日报" in zh_ceo
    assert "周度研究复盘" in zh_ceo
    assert "审计包" in zh_ceo
    assert "数据质量报告" in zh_ceo
    assert "风控报告" in zh_ceo
    assert "执行对账报告" in zh_ceo
    assert "工程摘要" in zh_ceo
    assert "发布审计" in zh_ceo
    assert "运行节奏" in zh_ceo
    assert "运行后台节奏" in zh_ceo
    assert "通知报告" in zh_ceo
    assert "通知状态" in zh_ceo
    assert "已发送" in zh_ceo
    assert "节奏状态" in zh_ceo
    assert "会话数" in zh_ceo
    assert "已生成" in zh_ceo
    assert "已跳过" in zh_ceo
    assert "提交纸面订单" in zh_ceo
    assert "纸面订单预览" in zh_ceo
    assert "纸面订单对账" in zh_ceo
    assert "订单号" in zh_ceo
    assert "对账后现金" in zh_ceo
    assert "对账后市值" in zh_ceo
    assert "已提交" in zh_ceo
    assert "订单已撤销" in zh_ceo
    assert "审批请求已取消" in zh_ceo
    assert "风控门" in zh_ceo
    assert "运行证据" in zh_ceo
    assert "运行时间线" in zh_ceo
    assert "Reports" in en_ceo
    assert "Report Type" in en_ceo
    assert "Generate Report" in en_ceo
    assert "Daily Brief" in en_ceo
    assert "Weekly Review" in en_ceo
    assert "Audit Pack" in en_ceo
    assert "Data Quality Report" in en_ceo
    assert "Risk Report" in en_ceo
    assert "Execution Reconciliation" in en_ceo
    assert "Engineering Digest" in en_ceo
    assert "Release Audit" in en_ceo
    assert "Run Rhythm" in en_ceo
    assert "Run Scheduled Rhythm" in en_ceo
    assert "Notify Report" in en_ceo
    assert "Notification Status" in en_ceo
    assert "Sent" in en_ceo
    assert "Rhythm Status" in en_ceo
    assert "Sessions" in en_ceo
    assert "Generated" in en_ceo
    assert "Skipped" in en_ceo
    assert "Submit Paper Order" in en_ceo
    assert "Paper Order Preview" in en_ceo
    assert "Paper Reconciliation" in en_ceo
    assert "Order ID" in en_ceo
    assert "Cash After" in en_ceo
    assert "Market Value After" in en_ceo
    assert "Submitted" in en_ceo
    assert "Order Canceled" in en_ceo
    assert "Approval Request Canceled" in en_ceo
    assert "Risk Gate" in en_ceo
    assert "Run Evidence" in en_ceo
    assert "Run Timeline" in en_ceo
    assert "实盘就绪" in zh_ceo
    assert "实盘红灯" in zh_ceo
    assert "激活红灯" in zh_ceo
    assert "解除红灯" in zh_ceo
    assert "运行实盘对账" in zh_ceo
    assert "实盘对账" in zh_ceo
    assert "Live Readiness" in en_ceo
    assert "Live Kill Switch" in en_ceo
    assert "Activate Kill Switch" in en_ceo
    assert "Deactivate Kill Switch" in en_ceo
    assert "Run Live Reconciliation" in en_ceo
    assert "Live Reconciliation" in en_ceo


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
    assert "agentRunSessionReadOnlyActions" in agent_api
    assert "/api/agent/sessions/${encodeURIComponent(sessionId)}/run-readonly" in agent_api
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
    assert "agentAutonomyStep" in agent_api
    assert "/api/agent/sessions/${encodeURIComponent(sessionId)}/autonomy-step" in agent_api
    assert "planner_mode?: string" in agent_api
    assert "semantic_draft?: Record<string, unknown>" in agent_api
    assert "planning_mode: string" in agent_types
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
    assert "export interface AgentReadOnlyWorkflow" in agent_types
    assert "export interface AgentReadOnlyWorkflowResponse" in agent_types
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
