import { get, patch, post } from "../client";
import type {
  AgentAction,
  AgentActionDetail,
  AgentAddMessageResponse,
  AgentActionsResponse,
  AgentDesksResponse,
  AgentEvidenceResponse,
  AgentHandoff,
  AgentHandoffsResponse,
  AgentLiveReadinessResponse,
  AgentPaperSubmitResponse,
  AgentReportResponse,
  AgentReportsResponse,
  AgentRunActionResponse,
  AgentSession,
  AgentSessionDetail,
  AgentSessionsResponse,
} from "../types";

export const agentApi = {
  agentSessions: () => get<AgentSessionsResponse>("/api/agent/sessions"),
  agentCreateSession: (payload: { title: string; default_desk?: string; tags?: string[] }) =>
    post<{ session: AgentSession }>("/api/agent/sessions", payload),
  agentSession: (sessionId: string) => get<AgentSessionDetail>(`/api/agent/sessions/${encodeURIComponent(sessionId)}`),
  agentUpdateSession: (
    sessionId: string,
    payload: { title?: string; status?: string; default_desk?: string; tags?: string[] },
  ) => patch<{ session: AgentSession }>(`/api/agent/sessions/${encodeURIComponent(sessionId)}`, payload),
  agentAddMessage: (
    sessionId: string,
    payload: { role?: string; desk?: string; content: string; evidence_refs?: string[]; action_refs?: string[] },
  ) => post<AgentAddMessageResponse>(`/api/agent/sessions/${encodeURIComponent(sessionId)}/messages`, payload),
  agentActions: (sessionId = "") =>
    get<AgentActionsResponse>(`/api/agent/actions${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`),
  agentHandoffs: (sessionId = "") =>
    get<AgentHandoffsResponse>(`/api/agent/handoffs${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`),
  agentResolveHandoff: (handoffId: string) =>
    post<{ handoff: AgentHandoff }>(`/api/agent/handoffs/${encodeURIComponent(handoffId)}/resolve`),
  agentAction: (actionId: string) => get<AgentActionDetail>(`/api/agent/actions/${encodeURIComponent(actionId)}`),
  agentApproveAction: (actionId: string) => post<{ action: AgentAction }>(`/api/agent/actions/${encodeURIComponent(actionId)}/approve`),
  agentRejectAction: (actionId: string, reason = "") =>
    post<{ action: AgentAction }>(`/api/agent/actions/${encodeURIComponent(actionId)}/reject`, { reason }),
  agentCancelAction: (actionId: string, reason = "") =>
    post<{ action: AgentAction }>(`/api/agent/actions/${encodeURIComponent(actionId)}/cancel`, { reason }),
  agentRunAction: (actionId: string) => post<AgentRunActionResponse>(`/api/agent/actions/${encodeURIComponent(actionId)}/run`),
  agentPaperSubmitAction: (actionId: string) =>
    post<AgentPaperSubmitResponse>(`/api/agent/paper/actions/${encodeURIComponent(actionId)}/submit`),
  agentReports: (sessionId = "") =>
    get<AgentReportsResponse>(`/api/agent/reports${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`),
  agentGenerateReport: (payload: { kind: string; session_id: string }) => post<AgentReportResponse>("/api/agent/reports", payload),
  agentLiveReadiness: () => get<AgentLiveReadinessResponse>("/api/agent/live/readiness"),
  agentEvidence: (evidenceId: string) => get<AgentEvidenceResponse>(`/api/agent/evidence/${encodeURIComponent(evidenceId)}`),
  agentDesks: () => get<AgentDesksResponse>("/api/agent/desks"),
};
