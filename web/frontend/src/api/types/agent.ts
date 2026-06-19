import type { SystemLlmProviderOption, SystemLlmRuntimeProfile } from "./system";

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

export interface AgentModelRuntimeResponse {
  runtime: {
    use_case: string;
    provider: string;
    label: string;
    model: string;
    base_url: string;
    credential_env: string;
    configured: boolean;
    enabled: boolean;
    protocol: string;
    block_reason: string;
  };
  reasoning: {
    level: string;
    provider_parameter: string;
    provider_value: string;
    temperature: number;
    response_format_json: boolean;
  };
  context: {
    status: string;
    max_tokens: number;
    used_tokens: number;
    raw_tokens: number;
    remaining_tokens: number;
    usage_pct: number;
    raw_usage_pct: number;
    message_count: number;
    estimator: string;
    thresholds: Record<string, number>;
    unknown_window: boolean;
    latest_pack: Record<string, unknown> | null;
  };
  profile: SystemLlmRuntimeProfile;
  options: {
    providers: SystemLlmProviderOption[];
    controlled_use_cases: string[];
  };
}

export interface AgentContextStatusResponse {
  context: {
    status: string;
    session_id: string;
    generated_at: string;
    thresholds: Record<string, number>;
    max_tokens: number;
    unknown_window: boolean;
    raw_tokens: number;
    effective_tokens: number;
    remaining_tokens: number;
    usage_pct: number;
    raw_usage_pct: number;
    message_count: number;
    input_signature: string;
    latest_pack: Record<string, unknown> | null;
  };
}

export interface AgentContextCompactResponse {
  pack: Record<string, unknown>;
  evidence: EvidenceRef | null;
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

export interface AgentAutonomyStep {
  status: string;
  mode: string;
  session_id: string;
  desk: string;
  checked_at: string;
  message: AgentMessage;
  desk_response: AgentDeskResponse;
  actions: AgentAction[];
  action_count: number;
  run_count: number;
  failed_count: number;
  blocked_count: number;
  skipped_count: number;
  runs: AgentRun[];
  skipped: Array<Record<string, unknown>>;
  boundary: Record<string, unknown>;
}

export interface AgentAutonomyRun {
  status: string;
  mode: string;
  session_id: string;
  desk: string;
  checked_at: string;
  max_steps: number;
  step_count: number;
  stop_reason: string;
  action_count: number;
  run_count: number;
  failed_count: number;
  blocked_count: number;
  skipped_count: number;
  steps: Array<AgentAutonomyStep & { step_index: number }>;
  boundary: Record<string, unknown>;
}

export interface AgentProgramPhase {
  index: number;
  phase_id: string;
  status: string;
  desk: string;
  action_type: string;
  tool_id: string;
  risk_level: string;
  summary: string;
  expected_effect: string;
  parameters: Record<string, unknown>;
  evidence: AgentWorkflowPlanAction["evidence"];
  action_id?: string;
  run_id?: string;
  evidence_refs?: string[];
}

export interface AgentProgramBlockedItem {
  desk: string;
  tool_id: string;
  risk_level: string;
  summary: string;
  reason: string;
  raw_reason?: string;
}

export interface AgentProgram {
  program_id: string;
  session_id: string;
  goal: string;
  desk: string;
  status: string;
  planning_mode: string;
  max_steps: number;
  current_step: number;
  phases: AgentProgramPhase[];
  blocked_items: AgentProgramBlockedItem[];
  boundary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  phase_count: number;
  safe_action_count: number;
  blocked_item_count: number;
}

export interface AgentProgramRun {
  status: string;
  program_id: string;
  session_id: string;
  checked_at: string;
  stop_reason?: string;
  step_count: number;
  run_count: number;
  failed_count?: number;
  blocked_count?: number;
  blocked_item_count: number;
  phases?: AgentProgramPhase[];
  runs?: AgentRun[];
  program: AgentProgram;
  boundary: Record<string, unknown>;
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
  resolution: string;
  resolved_at: string | null;
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

export interface AgentLiveEnvironment {
  status: string;
  broker: string;
  mode: string;
  enabled: boolean;
  paper_fallback: boolean;
  account_id_masked: string;
  checked_at: string;
  blockers: string[];
  checks: Record<string, Record<string, unknown>>;
  terminal_probe: Record<string, unknown>;
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
  broker_canceled_count?: number;
  broker_cancel_failed_count?: number;
  broker_cancellations?: Array<Record<string, unknown>>;
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

export interface AgentLiveMonitor {
  status: string;
  checked_at: string;
  session_id: string;
  readiness: Record<string, unknown>;
  kill_switch: AgentLiveKillSwitch;
  reconciliation: AgentLiveReconciliation;
  paper_fallback: boolean;
  path: string;
  evidence: EvidenceRef;
}

export interface AgentDeskResponse {
  message: AgentMessage;
  answer: string;
  confidence: number;
  evidence_refs: string[];
  proposed_actions: string[];
  blockers: string[];
  handoffs: AgentHandoff[];
  reasoning: AgentReasoningRow[];
  planning_mode: string;
}

export interface AgentReasoningRow {
  kind: string;
  [key: string]: unknown;
}

export interface AgentWorkflowPlanAction {
  desk: string;
  action_type: string;
  tool_id: string;
  risk_level: string;
  status_preview: string;
  approval_required: boolean;
  summary: string;
  expected_effect: string;
  parameters: Record<string, unknown>;
  evidence: {
    label: string;
    uri: string;
    summary: string;
  };
}

export interface AgentWorkflowPlan {
  status: string;
  desk: string;
  answer: string;
  confidence: number;
  planning_mode: string;
  actions: AgentWorkflowPlanAction[];
  handoffs: Array<Record<string, unknown>>;
  work_orders: Array<Record<string, unknown>>;
  blockers: string[];
  reasoning: AgentReasoningRow[];
  side_effects: Record<string, unknown>;
}

export interface AgentDesk {
  desk_id: string;
  display_name: string;
  mandate: string;
  capabilities?: string[];
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

export interface AgentSessionStreamSnapshot {
  status: string;
  session_id: string;
  generated_at: string;
  session: AgentSession;
  counts: {
    messages: number;
    actions: number;
    runs: number;
    run_events: number;
    handoffs: number;
    work_orders: number;
  };
  latest: Record<string, string>;
  signature: string;
}

export interface AgentRunStreamSnapshot {
  status: string;
  run_id: string;
  action_id: string;
  generated_at: string;
  run: AgentRun;
  counts: {
    events: number;
  };
  latest: {
    event_id: string;
    event_type: string;
    event_status: string;
  };
  events: AgentRunEvent[];
  signature: string;
}

export interface AgentAutonomyStepResponse {
  step: AgentAutonomyStep;
}

export interface AgentAutonomyRunResponse {
  run: AgentAutonomyRun;
}

export interface AgentProgramsResponse {
  status: string;
  programs: AgentProgram[];
  total: number;
  filters?: Record<string, string>;
}

export interface AgentProgramResponse {
  program: AgentProgram;
}

export interface AgentProgramRunResponse {
  run: AgentProgramRun;
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

export interface AgentActionFilters {
  session_id?: string;
  status?: string;
  desk?: string;
  risk_level?: string;
}

export interface AgentActionsResponse {
  actions: AgentAction[];
  total: number;
  filters?: AgentActionFilters;
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

export interface AgentWorkOrderResponse {
  work_order: AgentWorkOrder;
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

export interface AgentLiveEnvironmentResponse {
  environment: AgentLiveEnvironment;
}

export interface AgentLiveKillSwitchResponse {
  kill_switch: AgentLiveKillSwitch;
}

export interface AgentLiveReconciliationResponse {
  reconciliation: AgentLiveReconciliation;
}

export interface AgentLiveMonitorResponse {
  monitor: AgentLiveMonitor;
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

export interface AgentWorkflowPlanResponse {
  plan: AgentWorkflowPlan;
}
