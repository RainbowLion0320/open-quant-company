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

export interface DeepSeekUsageResponse {
  data: any[];
  source?: string;
  balance?: {
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

export interface HindsightGraphResponse {
  nodes: any[];
  links: any[];
  stats?: Record<string, any>;
}
