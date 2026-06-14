import { get, post } from "../client";
import type {
  AgentAction,
  AgentActionsResponse,
  AgentDesksResponse,
  AgentEvidenceResponse,
  AgentRun,
  AgentMessage,
  AgentSession,
  AgentSessionDetail,
  AgentSessionsResponse,
} from "../types";

export const agentApi = {
  agentSessions: () => get<AgentSessionsResponse>("/api/agent/sessions"),
  agentCreateSession: (payload: { title: string; default_desk?: string; tags?: string[] }) =>
    post<{ session: AgentSession }>("/api/agent/sessions", payload),
  agentSession: (sessionId: string) => get<AgentSessionDetail>(`/api/agent/sessions/${encodeURIComponent(sessionId)}`),
  agentAddMessage: (
    sessionId: string,
    payload: { role?: string; desk?: string; content: string; evidence_refs?: string[]; action_refs?: string[] },
  ) => post<{ message: AgentMessage }>(`/api/agent/sessions/${encodeURIComponent(sessionId)}/messages`, payload),
  agentActions: (sessionId = "") =>
    get<AgentActionsResponse>(`/api/agent/actions${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`),
  agentAction: (actionId: string) => get<{ action: AgentAction; runs: AgentRun[] }>(`/api/agent/actions/${encodeURIComponent(actionId)}`),
  agentApproveAction: (actionId: string) => post<{ action: AgentAction }>(`/api/agent/actions/${encodeURIComponent(actionId)}/approve`),
  agentRejectAction: (actionId: string, reason = "") =>
    post<{ action: AgentAction }>(`/api/agent/actions/${encodeURIComponent(actionId)}/reject`, { reason }),
  agentEvidence: (evidenceId: string) => get<AgentEvidenceResponse>(`/api/agent/evidence/${encodeURIComponent(evidenceId)}`),
  agentDesks: () => get<AgentDesksResponse>("/api/agent/desks"),
};
