export interface SystemMonitor {
  timestamp: string;
  cpu: { percent: number; freq_current: number | null; cores_physical: number; cores_logical: number; load_avg: number[] };
  memory: { total_gb: number; used_gb: number; percent: number };
  disk: { total_gb: number; used_gb: number; percent: number };
  battery: { percent: number; charging: boolean; minutes_left: number | null } | null;
  top_processes: { pid: number; name: string; cpu: number; mem: number }[];
  token: {
    hermes: { input_tokens: number; output_tokens: number; total_tokens: number; sessions: number; messages: number; tool_calls: number; api_calls: number; cost_usd: number };
    external: { input_tokens: number; output_tokens: number; total_tokens: number; calls: number; cost_usd: number; sources: string[] };
    total: { input_tokens: number; output_tokens: number; total_tokens: number; cost_usd: number };
    updated_at: string | null;
  };
}

export interface SystemHistoryResponse {
  hours: number;
  points: number;
  data: any[];
}

export interface SystemLlmRuntimeProfile {
  source: "settings" | "global_override" | string;
  provider: string;
  model: string;
  reasoning_mode: string;
  updated_at: string;
}

export interface SystemLlmReasoningMode {
  key: string;
  label: string;
  description: string;
  enabled: boolean;
}

export interface SystemLlmProviderOption {
  provider: string;
  label: string;
  enabled: boolean;
  configured: boolean;
  protocol: string;
  credential_env: string;
  secret_status: string;
  models: string[];
  model_discovery: SystemLlmModelDiscovery;
  reasoning_modes: SystemLlmReasoningMode[];
}

export interface SystemLlmRuntimeResponse {
  profile: SystemLlmRuntimeProfile;
  providers: SystemLlmProviderOption[];
  controlled_use_cases: string[];
}

export interface SystemLlmModelDiscovery {
  status: string;
  endpoint: string;
  error: string;
  discovered_at: string;
  discovered_models: string[];
}

export interface SystemLlmModelDiscoveryResponse {
  discovery: SystemLlmModelDiscovery & {
    provider: string;
    models?: string[];
  };
  runtime: SystemLlmRuntimeResponse;
}

export interface DbHealthResponse {
  data: any[];
  summary: any | null;
  status: "ok" | "no_data" | "error";
  message?: string;
  checked_at?: string | null;
  api_fallback?: boolean;
}

export interface DbRepairResponse {
  status: "started" | "conflict" | "failed" | "not_found" | string;
  job_id?: string;
  table?: string;
  message?: string;
}

export interface DbRepairBatchResponse {
  status: "started" | "empty" | "failed" | string;
  total: number;
  started: number;
  jobs: DbRepairResponse[];
}

export interface CodeGraphStatusResponse {
  initialized: boolean;
  file_count: number;
  node_count: number;
  edge_count: number;
  db_size_bytes?: number;
  backend?: string;
  languages: { language: string; files: number; nodes: number }[];
  nodes_by_kind: Record<string, number>;
  pending_changes: { added: number; modified: number; removed: number };
  stale: boolean;
  message?: string;
  truncated?: boolean;
}

export interface CodeGraphNode {
  id: string;
  label: string;
  kind: string;
  path: string;
  qualified_name: string;
  language: string;
  start_line: number | null;
  end_line: number | null;
  count: number;
  degree: number;
  group: string;
  signature?: string | null;
  docstring?: string | null;
}

export interface CodeGraphIssue {
  id: string;
  severity: "P0" | "P1" | "P2";
  category: string;
  title: string;
  node_id: string;
  source: string;
  target: string;
  path: string;
  evidence: Record<string, any>;
  recommendation: string;
}

export interface CodeGraphNodeRisk {
  score: number;
  severity: "P0" | "P1" | "P2";
  categories: string[];
}

export interface CodeGraphEdgeFlag {
  source: string;
  target: string;
  category: string;
  severity: "P0" | "P1" | "P2";
}

export interface CodeGraphDiagnosticsResponse {
  summary: {
    initialized: boolean;
    issue_count: number;
    total_issue_count: number;
    severity_counts: Record<string, number>;
    risk_score: number;
    git_churn_available: boolean;
    stale: boolean;
    truncated: boolean;
  };
  issues: CodeGraphIssue[];
  node_scores: Record<string, CodeGraphNodeRisk>;
  edge_flags: CodeGraphEdgeFlag[];
}

export interface CodeGraphLink {
  source: string;
  target: string;
  type: string;
  label: string;
  count: number;
  direction: string;
}

export interface CodeGraphGraphResponse {
  level: "module" | "file" | "symbol" | "neighborhood";
  nodes: CodeGraphNode[];
  links: CodeGraphLink[];
  stats: CodeGraphStatusResponse;
}

export interface TestDesignSummary {
  test_count: number;
  file_count: number;
  target_count: number;
  spec_count: number;
  risk_count: number;
  risk_covered: number;
  risk_coverage_rate: number;
  target_link_rate: number;
  spec_link_rate: number;
  smell_count: number;
  severity_counts: Record<string, number>;
  design_score: number;
  truncated: boolean;
  artifact_age_seconds?: number | null;
}

export interface TestDesignRiskRow {
  key: string;
  label_zh?: string;
  label_en?: string;
  counts: Record<string, number>;
  total: number;
}

export interface TestDesignGraphNode {
  id: string;
  label: string;
  kind: string;
  group: string;
  path?: string;
  count?: number;
}

export interface TestDesignGraphLink {
  source: string;
  target: string;
  type: string;
  label: string;
  count: number;
}

export interface TestDesignCase {
  nodeid: string;
  file: string;
  name: string;
  line: number;
  kind: string;
  domain: string;
  risks: string[];
  target_modules: string[];
  specs: string[];
  fixtures: string[];
  markers: string[];
  assert_count: number;
  raises_count: number;
  mock_count: number;
  smells: string[];
}

export interface TestDesignSmell {
  id: string;
  severity: "P0" | "P1" | "P2" | string;
  kind: string;
  title: string;
  subject: string;
  path: string;
  evidence: Record<string, any>;
  recommendation: string;
}

export interface TestDesignResponse {
  status: "no_artifact" | "ok" | "empty" | string;
  generated_at?: string;
  latest: { generated_at?: string; artifact_path?: string } | null;
  summary: TestDesignSummary;
  matrix: { kinds: string[]; risks: TestDesignRiskRow[] };
  graph: { nodes: TestDesignGraphNode[]; links: TestDesignGraphLink[] };
  cases: TestDesignCase[];
  smells: TestDesignSmell[];
  recommended_command: string;
}

export interface AstIntelligenceSummary {
  file_count: number;
  unit_count: number;
  issue_count: number;
  clone_group_count: number;
  languages: Record<string, number>;
  severity_counts: Record<string, number>;
  duplicate_score: number;
  truncated?: boolean;
  artifact_age_seconds?: number | null;
}

export interface AstUnitRef {
  id: string;
  path: string;
  language: string;
  kind: string;
  name: string;
  start_line: number;
  end_line: number;
  node_count: number;
}

export interface AstIssue {
  id: string;
  severity: "P0" | "P1" | "P2" | string;
  category: string;
  title: string;
  paths: string[];
  units: AstUnitRef[];
  language: string;
  evidence: Record<string, any>;
  recommendation: string;
}

export interface AstCloneGroup {
  id: string;
  category: string;
  similarity: number;
  units: AstUnitRef[];
  shared_shape: string;
  module_pairs: string[];
}

export interface AstGraphNode {
  id: string;
  label: string;
  kind: string;
  group: string;
  path?: string;
  count?: number;
}

export interface AstGraphLink {
  source: string;
  target: string;
  type: string;
  label: string;
  count: number;
}

export interface AstIntelligenceResponse {
  status: "no_artifact" | "ok" | "empty" | "error" | string;
  generated_at?: string;
  latest: { generated_at?: string; artifact_path?: string } | null;
  summary: AstIntelligenceSummary;
  issues: AstIssue[];
  clone_groups: AstCloneGroup[];
  graph: { nodes: AstGraphNode[]; links: AstGraphLink[] };
  errors: { path?: string; language?: string; message?: string; line?: number }[];
  recommended_command: string;
}

export interface LifecycleCheck {
  status: string;
  summary?: Record<string, any>;
  blockers?: string[];
  warnings?: string[];
  [key: string]: any;
}

export interface LifecycleResponse {
  schema_version?: number;
  status: "no_artifact" | "ok" | "blocked" | string;
  generated_at?: string;
  latest: { generated_at?: string; artifact_path?: string } | null;
  artifact_age_seconds?: number | null;
  checks: Record<string, LifecycleCheck>;
  blockers: string[];
  warnings: string[];
  recommended_command: string;
}
