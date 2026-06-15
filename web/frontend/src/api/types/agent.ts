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
  expires_at: string;
  created_at: string;
  updated_at: string;
}

export interface EvidenceRef {
  evidence_id: string;
  kind: string;
  label: string;
  uri: string;
  snapshot_uri: string;
  summary: string;
  generated_at: string;
  hash: string;
  current_hash?: string;
  freshness_status: string;
}

export interface AgentEvidenceSnapshot {
  uri: string;
  hash: string;
}

export interface EvidenceNavigation {
  kind: string;
  href: string;
  label: string;
}

export interface AgentRunEvent {
  event_id: string;
  run_id: string;
  action_id: string;
  sequence: number;
  event_type: string;
  status: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
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
  events?: AgentRunEvent[];
}

export interface AgentReadOnlyWorkflow {
  status: string;
  session_id: string;
  checked_at: string;
  action_count: number;
  run_count: number;
  succeeded_count: number;
  failed_count: number;
  blocked_count: number;
  skipped_count: number;
  runs: AgentRun[];
  skipped: Array<Record<string, unknown>>;
}

export interface AgentApprovalPolicy {
  policy_id: string;
  risk_level: string;
  default_decision: string;
  required_role: string;
  expires_after_seconds: number;
  reason: string;
  approval_required: boolean;
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

export interface AgentWorkOrder {
  work_order_id: string;
  session_id: string;
  desk: string;
  title: string;
  summary: string;
  impact: string;
  affected_files: string[];
  suggested_verification: string[];
  evidence_refs: string[];
  status: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface AgentReport {
  report_id: string;
  session_id: string;
  kind: string;
  title: string;
  summary: string;
  path: string;
  markdown_path: string;
  evidence_id: string;
  evidence_refs: string[];
  missing_evidence: string[];
  artifact_context?: Record<string, unknown>;
  sections: Array<Record<string, unknown>>;
  generated_at: string;
}

export interface AgentLiveReadiness {
  broker: string;
  mode: string;
  enabled: boolean;
  sdk_available: boolean;
  logged_in: boolean;
  account_id_masked: string;
  permissions: string[];
  kill_switch: boolean;
  paper_fallback: boolean;
  last_probe_at: string;
  blockers: string[];
  live_kill_switch?: AgentLiveKillSwitch;
}

export interface AgentLiveKillSwitch {
  status: string;
  active: boolean;
  reason: string;
  activated_at: string;
  deactivated_at: string;
  updated_at: string;
  paper_fallback: boolean;
  state_path?: string;
  artifact_path?: string;
  canceled_count?: number;
  canceled_actions?: AgentAction[];
  read_error?: string;
  evidence?: EvidenceRef;
}

export interface AgentLiveReconciliation {
  status: string;
  checked_at: string;
  session_id: string;
  action_count: number;
  reconciled_count: number;
  skipped_count: number;
  blocked_count: number;
  failed_count: number;
  paper_fallback: boolean;
  items: Array<Record<string, unknown>>;
  path?: string;
  evidence?: EvidenceRef;
}

export interface AgentDeskResponse {
  message: AgentMessage;
  answer: string;
  confidence: number;
  evidence_refs: string[];
  proposed_actions: string[];
  blockers: string[];
  handoffs: AgentHandoff[];
}

export interface AgentDesk {
  desk_id: string;
  display_name: string;
  mandate: string;
  allowed_tools: string[];
  forbidden_actions: string[];
  evidence_required: string[];
  handoff_targets: string[];
  default_policy: string;
  status: string;
}

export interface AgentSessionDetail {
  session: AgentSession;
  messages: AgentMessage[];
  actions: AgentAction[];
  runs: AgentRun[];
  handoffs: AgentHandoff[];
  work_orders: AgentWorkOrder[];
}

export interface AgentReadOnlyWorkflowResponse {
  workflow: AgentReadOnlyWorkflow;
}

export interface AgentActionDetail {
  action: AgentAction;
  runs: AgentRun[];
  paper_reconciliations: AgentPaperReconciliation[];
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

export interface AgentApprovalPoliciesResponse {
  policies: AgentApprovalPolicy[];
  total: number;
}

export interface AgentHandoffsResponse {
  handoffs: AgentHandoff[];
  total: number;
}

export interface AgentWorkOrdersResponse {
  status: string;
  work_orders: AgentWorkOrder[];
  total: number;
}

export interface AgentReportsResponse {
  status: string;
  reports: AgentReport[];
  total: number;
}

export interface AgentReportResponse {
  report: AgentReport;
}

export interface AgentReportNotificationChannel {
  channel: string;
  status: string;
  configured: boolean;
  required_env: string[];
  missing_env: string[];
  error: string;
  status_code: number | null;
  provider_message_id?: string;
}

export interface AgentReportNotification {
  status: string;
  notification_id: string;
  report_id: string;
  session_id: string;
  report_kind: string;
  report_title: string;
  report_path: string;
  report_evidence_id: string;
  dry_run: boolean;
  checked_at: string;
  sent_count: number;
  failed_count: number;
  blocked_count: number;
  channels: AgentReportNotificationChannel[];
  message_preview: Record<string, unknown>;
  path: string;
  evidence: EvidenceRef;
}

export interface AgentReportNotificationResponse {
  notification: AgentReportNotification;
}

export interface AgentReportRhythmItem {
  kind: string;
  title: string;
  cadence: string;
  interval_hours: number;
  last_generated_at: string;
  due: boolean;
  reason: string;
  status: string;
  report_id: string;
  evidence_id: string;
  generated_at?: string;
}

export interface AgentReportRhythm {
  status: string;
  run_id: string;
  session_id: string;
  checked_at: string;
  force: boolean;
  generated_count: number;
  skipped_count: number;
  notification_count: number;
  notification_failed_count: number;
  items: AgentReportRhythmItem[];
  reports: AgentReport[];
  notifications: AgentReportNotification[];
  path: string;
  evidence: EvidenceRef;
}

export interface AgentReportRhythmResponse {
  rhythm: AgentReportRhythm;
}

export interface AgentScheduledReportRhythmSession {
  session_id: string;
  status: string;
  generated_count: number;
  skipped_count: number;
  notification_count: number;
  notification_failed_count: number;
  rhythm_run_id: string;
  path: string;
  evidence_id: string;
  error?: string;
}

export interface AgentScheduledReportRhythm {
  status: string;
  schedule_id: string;
  checked_at: string;
  force: boolean;
  session_status: string;
  session_count: number;
  generated_count: number;
  skipped_count: number;
  notification_count: number;
  notification_failed_count: number;
  failed_count: number;
  sessions: AgentScheduledReportRhythmSession[];
  path: string;
  evidence: EvidenceRef;
}

export interface AgentScheduledReportRhythmResponse {
  schedule: AgentScheduledReportRhythm;
}

export interface AgentLiveReadinessResponse {
  health: AgentLiveReadiness;
}

export interface AgentLiveKillSwitchResponse {
  kill_switch: AgentLiveKillSwitch;
}

export interface AgentLiveReconciliationResponse {
  reconciliation: AgentLiveReconciliation;
}

export interface AgentEvidenceResponse {
  status: string;
  evidence_id: string;
  evidence: EvidenceRef | null;
  snapshot: AgentEvidenceSnapshot | null;
  navigation: EvidenceNavigation | null;
}

export interface AgentRunActionResponse {
  run: AgentRun;
}

export interface AgentPaperSubmission {
  status: string;
  preview: Record<string, unknown>;
  run: AgentRun;
  reconciliation: Record<string, unknown>;
  evidence: EvidenceRef;
}

export interface AgentPaperCancellation {
  status: string;
  run: AgentRun;
  reconciliation: Record<string, unknown>;
  evidence: EvidenceRef;
}

export interface AgentPaperReconciliation {
  action_id: string;
  session_id: string;
  status: string;
  order_id: string;
  error: string;
  cancel_reason?: string;
  preview: Record<string, unknown>;
  account_after: Record<string, unknown>;
  positions_after: Array<Record<string, unknown>>;
  orders_after: Array<Record<string, unknown>>;
  generated_at: string;
  evidence_id: string;
  path: string;
  run_id: string;
  freshness_status: string;
}

export interface AgentPaperSubmitResponse {
  submission: AgentPaperSubmission;
}

export interface AgentPaperCancelResponse {
  cancellation: AgentPaperCancellation;
}

export interface AgentAddMessageResponse {
  message: AgentMessage;
  desk_response?: AgentDeskResponse;
}
