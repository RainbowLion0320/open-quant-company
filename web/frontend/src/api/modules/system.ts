import { get, patch, post } from "../client";
import type { AstIntelligenceResponse, CodeGraphDiagnosticsResponse, CodeGraphGraphResponse, CodeGraphNode, CodeGraphStatusResponse, DbHealthResponse, DbRepairBatchResponse, DbRepairResponse, LifecycleResponse, LlmUsageResponse, SystemHistoryResponse, SystemLlmModelDiscoveryResponse, SystemLlmRuntimeResponse, SystemMonitor, TestDesignResponse } from "../types";

function queryString(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const query = search.toString();
  return query ? `?${query}` : "";
}

export const systemApi = {
  systemMonitor: () => get<SystemMonitor>("/api/system/monitor"),
  systemHistory: (hours = 24) => get<SystemHistoryResponse>(`/api/system/history?hours=${hours}`),
  llmUsage: () => get<LlmUsageResponse>("/api/system/llm-usage"),
  systemLlmRuntime: () => get<SystemLlmRuntimeResponse>("/api/system/llm-runtime"),
  updateSystemLlmRuntime: (payload: { provider?: string; model?: string; reasoning_mode?: string; reset?: boolean }) =>
    patch<SystemLlmRuntimeResponse>("/api/system/llm-runtime", payload),
  discoverSystemLlmRuntimeModels: (provider: string) =>
    post<SystemLlmModelDiscoveryResponse>(`/api/system/llm-runtime/providers/${encodeURIComponent(provider)}/models/discover`),
  apiHealth: () => get<{ items: { name: string; status: string; detail: string }[]; summary: string; all_ok: boolean }>("/api/system/api-health"),
  cronJobs: () => get<{ jobs: { name: string; schedule: string; last_run: string | null; last_status: string | null; next_run: string | null; enabled: boolean; state: string; no_agent: boolean }[]; summary: string }>("/api/system/cron-jobs"),
  dbHealth: () => get<DbHealthResponse>("/api/system/db-health"),
  dbHealthRepairAll: (tables: string[]) => post<DbRepairBatchResponse>("/api/system/db-health/repair", { tables }),
  dbHealthRepairStatus: (jobId: string) => get<DbRepairResponse>(`/api/system/db-health/repair-status/${encodeURIComponent(jobId)}`),
  auditHistory: (section = "", limit = 50) =>
    get<{ entries: any[]; summary: any; total: number }>(`/api/system/audit?section=${encodeURIComponent(section)}&limit=${limit}`),
  authStatus: () => get<{ has_api_key: boolean; status: string }>("/api/system/auth"),
  testDesign: () => get<TestDesignResponse>("/api/system/tests/design"),
  astIntelligence: () => get<AstIntelligenceResponse>("/api/system/ast-intelligence"),
  lifecycle: () => get<LifecycleResponse>("/api/system/lifecycle"),
  codeGraphStatus: () => get<CodeGraphStatusResponse>("/api/codegraph/status"),
  codeGraphGraph: (params: { level?: string; root?: string; edge_kinds?: string; node_kinds?: string; limit?: number } = {}) =>
    get<CodeGraphGraphResponse>(`/api/codegraph/graph${queryString(params)}`),
  codeGraphSearch: (q: string, limit = 20) =>
    get<{ items: CodeGraphNode[] }>(`/api/codegraph/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  codeGraphNeighborhood: (nodeId: string, depth = 1, limit = 180) =>
    get<CodeGraphGraphResponse>(`/api/codegraph/neighborhood?node_id=${encodeURIComponent(nodeId)}&depth=${depth}&limit=${limit}`),
  codeGraphDiagnostics: (params: { scope?: string; root?: string; limit?: number; include_git?: boolean } = {}) =>
    get<CodeGraphDiagnosticsResponse>(`/api/codegraph/diagnostics${queryString(params)}`),
  codeGraphSync: (mode: "sync" | "rebuild") => post<{ status: string; mode: string; results: any[] }>("/api/codegraph/sync", { mode }),
};
