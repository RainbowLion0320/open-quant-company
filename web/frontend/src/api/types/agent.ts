export interface AgentSession {
  session_id: string;
  title: string;
  status: string;
  created_by: string;
  default_desk: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface AgentMessage {
  message_id: string;
  session_id: string;
  role: string;
  desk: string;
  content: string;
  evidence_refs: string[];
  action_refs: string[];
  created_at: string;
}

export interface AgentAction {
  action_id: string;
  session_id: string;
  desk: string;
  action_type: string;
  risk_level: string;
  status: string;
  summary: string;
  parameters: Record<string, unknown>;
  expected_effect: string;
  evidence_refs: string[];
  approval_required: boolean;
  approval_decision: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface EvidenceRef {
  evidence_id: string;
  kind: string;
  label: string;
  uri: string;
  summary: string;
  generated_at: string;
  hash: string;
  freshness_status: string;
}

export interface EvidenceNavigation {
  kind: string;
  href: string;
  label: string;
}

export interface AgentRun {
  run_id: string;
  action_id: string;
  tool_name: string;
  command: string[];
  started_at: string;
  finished_at: string;
  status: string;
  return_code: number | null;
  stdout_summary: string;
  stderr_summary: string;
  artifact_refs: string[];
}

export interface AgentHandoff {
  handoff_id: string;
  session_id: string;
  source_message_id: string;
  source_desk: string;
  target_desk: string;
  reason: string;
  status: string;
  evidence_refs: string[];
  created_at: string;
  resolved_at: string;
}

export interface AgentDesk {
  desk_id: string;
  display_name: string;
  mandate: string;
  allowed_tools: string[];
  forbidden_actions: string[];
  handoff_targets: string[];
  status: string;
}

export interface AgentSessionDetail {
  session: AgentSession;
  messages: AgentMessage[];
  actions: AgentAction[];
  runs: AgentRun[];
  handoffs: AgentHandoff[];
}

export interface AgentActionDetail {
  action: AgentAction;
  runs: AgentRun[];
}

export interface AgentSessionsResponse {
  sessions: AgentSession[];
  total: number;
}

export interface AgentActionsResponse {
  actions: AgentAction[];
  total: number;
}

export interface AgentDesksResponse {
  desks: AgentDesk[];
  total: number;
}

export interface AgentHandoffsResponse {
  handoffs: AgentHandoff[];
  total: number;
}

export interface AgentEvidenceResponse {
  status: string;
  evidence_id: string;
  evidence: EvidenceRef | null;
  navigation: EvidenceNavigation | null;
}

export interface AgentRunActionResponse {
  run: AgentRun;
}
