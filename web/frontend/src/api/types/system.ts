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

export interface LlmUsageResponse {
  data: any[];
  source?: string;
  provider?: string;
  providers?: string[];
  balances?: Record<string, {
    provider?: string;
    label?: string;
    status: string;
    is_available: boolean;
    balance_infos: { currency: string; total_balance: string; granted_balance: string; topped_up_balance: string }[];
    message?: string;
  }>;
  balance?: {
    provider?: string;
    label?: string;
    status: string;
    is_available: boolean;
    balance_infos: { currency: string; total_balance: string; granted_balance: string; topped_up_balance: string }[];
    message?: string;
  };
  usage?: {
    status: string;
    daily: any[];
    models: string[];
    dates: string[];
    totals: { tokens: number; requests: number; estimated_cost_usd: number; estimated_cost_cny: number };
    pricing_source?: string;
  };
  total_cost?: number;
  status?: string;
  message?: string;
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
