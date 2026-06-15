import { get, patch, post, streamSse } from "../client";
import type {
  AgentAction,
  AgentActionDetail,
  AgentActionFilters,
  AgentAddMessageResponse,
  AgentActionsResponse,
  AgentApprovalPoliciesResponse,
  AgentDesksResponse,
  AgentEvidenceResponse,
  AgentHandoff,
  AgentHandoffsResponse,
  AgentLiveKillSwitchResponse,
  AgentLiveReconciliationResponse,
  AgentLiveReadinessResponse,
  AgentPaperCancelResponse,
  AgentReadOnlyWorkflowResponse,
  AgentReportNotificationResponse,
  AgentPaperSubmitResponse,
  AgentReportRhythmResponse,
  AgentReportResponse,
  AgentReportsResponse,
  AgentRunActionResponse,
  AgentScheduledReportRhythmResponse,
  AgentSession,
  AgentSessionDetail,
  AgentSessionStreamSnapshot,
  AgentWorkflowPlanResponse,
  AgentSessionsResponse,
  AgentWorkOrderResponse,
  AgentWorkOrdersResponse,
} from "../types";

export const agentApi = {
  agentSessions: () => get<AgentSessionsResponse>("/api/agent/sessions"),
  agentCreateSession: (payload: { title: string; default_desk?: string; tags?: string[] }) =>
    post<{ session: AgentSession }>("/api/agent/sessions", payload),
  agentSession: (sessionId: string) => get<AgentSessionDetail>(`/api/agent/sessions/${encodeURIComponent(sessionId)}`),
  agentSessionStreamUrl: (sessionId: string) => `/api/agent/sessions/${encodeURIComponent(sessionId)}/stream`,
  agentSessionStream: (
    sessionId: string,
    handlers: {
      onSnapshot: (snapshot: AgentSessionStreamSnapshot) => void;
      onMissing?: (payload: { status: string; session_id: string }) => void;
    },
    options: { signal?: AbortSignal } = {},
  ) => streamSse(
    `/api/agent/sessions/${encodeURIComponent(sessionId)}/stream`,
    {
      session_snapshot: data => handlers.onSnapshot(JSON.parse(data) as AgentSessionStreamSnapshot),
      session_missing: data => handlers.onMissing?.(JSON.parse(data) as { status: string; session_id: string }),
    },
    options,
  ),
  agentUpdateSession: (
    sessionId: string,
    payload: { title?: string; status?: string; default_desk?: string; tags?: string[] },
  ) => patch<{ session: AgentSession }>(`/api/agent/sessions/${encodeURIComponent(sessionId)}`, payload),
  agentRunSessionReadOnlyActions: (sessionId: string) =>
    post<AgentReadOnlyWorkflowResponse>(`/api/agent/sessions/${encodeURIComponent(sessionId)}/run-readonly`),
  agentAddMessage: (
    sessionId: string,
    payload: { role?: string; desk?: string; content: string; evidence_refs?: string[]; action_refs?: string[] },
  ) => post<AgentAddMessageResponse>(`/api/agent/sessions/${encodeURIComponent(sessionId)}/messages`, payload),
  agentPlan: (payload: { desk: string; content: string }) => post<AgentWorkflowPlanResponse>("/api/agent/plans", payload),
  agentActions: (filters: AgentActionFilters = {}) => {
    const params = new URLSearchParams();
    if (filters.session_id) params.set("session_id", filters.session_id);
    if (filters.status) params.set("status", filters.status);
    if (filters.desk) params.set("desk", filters.desk);
    if (filters.risk_level) params.set("risk_level", filters.risk_level);
    const query = params.toString();
    return get<AgentActionsResponse>(`/api/agent/actions${query ? `?${query}` : ""}`);
  },
  agentHandoffs: (sessionId = "") =>
    get<AgentHandoffsResponse>(`/api/agent/handoffs${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`),
  agentResolveHandoff: (handoffId: string) =>
    post<{ handoff: AgentHandoff }>(`/api/agent/handoffs/${encodeURIComponent(handoffId)}/resolve`),
  agentWorkOrders: (sessionId = "") =>
    get<AgentWorkOrdersResponse>(
      sessionId ? `/api/agent/work-orders?session_id=${encodeURIComponent(sessionId)}` : "/api/agent/work-orders",
    ),
  agentUpdateWorkOrder: (workOrderId: string, payload: { status: string; resolution?: string }) =>
    patch<AgentWorkOrderResponse>(`/api/agent/work-orders/${encodeURIComponent(workOrderId)}`, payload),
  agentAction: (actionId: string) => get<AgentActionDetail>(`/api/agent/actions/${encodeURIComponent(actionId)}`),
  agentApproveAction: (actionId: string) => post<{ action: AgentAction }>(`/api/agent/actions/${encodeURIComponent(actionId)}/approve`),
  agentRejectAction: (actionId: string, reason = "") =>
    post<{ action: AgentAction }>(`/api/agent/actions/${encodeURIComponent(actionId)}/reject`, { reason }),
  agentCancelAction: (actionId: string, reason = "") =>
    post<{ action: AgentAction }>(`/api/agent/actions/${encodeURIComponent(actionId)}/cancel`, { reason }),
  agentRunAction: (actionId: string) => post<AgentRunActionResponse>(`/api/agent/actions/${encodeURIComponent(actionId)}/run`),
  agentPaperSubmitAction: (actionId: string) =>
    post<AgentPaperSubmitResponse>(`/api/agent/paper/actions/${encodeURIComponent(actionId)}/submit`),
  agentPaperCancelAction: (actionId: string, reason = "") =>
    post<AgentPaperCancelResponse>(`/api/agent/paper/actions/${encodeURIComponent(actionId)}/cancel`, { reason }),
  agentReports: (sessionId = "") =>
    get<AgentReportsResponse>(`/api/agent/reports${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`),
  agentGenerateReport: (payload: { kind: string; session_id: string }) => post<AgentReportResponse>("/api/agent/reports", payload),
  agentNotifyReport: (reportId: string, payload: { channels?: string[]; dry_run?: boolean } = {}) =>
    post<AgentReportNotificationResponse>(`/api/agent/reports/${encodeURIComponent(reportId)}/notify`, payload),
  agentRunReportRhythm: (payload: { session_id: string; force?: boolean }) =>
    post<AgentReportRhythmResponse>("/api/agent/reports/rhythm", payload),
  agentRunScheduledReportRhythm: (payload: { force?: boolean } = {}) =>
    post<AgentScheduledReportRhythmResponse>("/api/agent/reports/rhythm/scheduled", payload),
  agentLiveReadiness: () => get<AgentLiveReadinessResponse>("/api/agent/live/readiness"),
  agentLiveKillSwitch: () => get<AgentLiveKillSwitchResponse>("/api/agent/live/kill-switch"),
  agentLiveKillSwitchActivate: (reason = "") =>
    post<AgentLiveKillSwitchResponse>("/api/agent/live/kill-switch/activate", { reason }),
  agentLiveKillSwitchDeactivate: (reason = "") =>
    post<AgentLiveKillSwitchResponse>("/api/agent/live/kill-switch/deactivate", { reason }),
  agentLiveReconciliation: (payload: { session_id?: string } = {}) =>
    post<AgentLiveReconciliationResponse>("/api/agent/live/reconciliation", payload),
  agentEvidence: (evidenceId: string) => get<AgentEvidenceResponse>(`/api/agent/evidence/${encodeURIComponent(evidenceId)}`),
  agentDesks: () => get<AgentDesksResponse>("/api/agent/desks"),
  agentApprovalPolicies: () => get<AgentApprovalPoliciesResponse>("/api/agent/policies"),
};
