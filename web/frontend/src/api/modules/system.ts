import { get, post } from "../client";
import type { AstIntelligenceResponse, CodeGraphDiagnosticsResponse, CodeGraphGraphResponse, CodeGraphNode, CodeGraphStatusResponse, DbHealthResponse, DbRepairResponse, LlmUsageResponse, SystemHistoryResponse, SystemMonitor, TestDesignResponse } from "../types";

export const systemApi = {
  systemMonitor: () => get<SystemMonitor>("/api/system/monitor"),
  systemHistory: (hours = 24) => get<SystemHistoryResponse>(`/api/system/history?hours=${hours}`),
  llmUsage: () => get<LlmUsageResponse>("/api/system/llm-usage"),
  apiHealth: () => get<{ items: { name: string; status: string; detail: string }[]; summary: string; all_ok: boolean }>("/api/system/api-health"),
  cronJobs: () => get<{ jobs: { name: string; schedule: string; last_run: string | null; last_status: string | null; next_run: string | null; enabled: boolean; state: string; no_agent: boolean }[]; summary: string }>("/api/system/cron-jobs"),
  dbHealth: () => get<DbHealthResponse>("/api/system/db-health"),
  dbHealthRepair: (table: string) => post<DbRepairResponse>(`/api/system/db-health/repair/${encodeURIComponent(table)}`),
  dbHealthRepairStatus: (jobId: string) => get<DbRepairResponse>(`/api/system/db-health/repair-status/${encodeURIComponent(jobId)}`),
  auditHistory: (section = "", limit = 50) =>
    get<{ entries: any[]; summary: any; total: number }>(`/api/system/audit?section=${encodeURIComponent(section)}&limit=${limit}`),
  systemMode: () => get<{ mode: string; has_api_key: boolean; allows_settings_write: boolean; allows_paper_trading: boolean; readonly_sections: string[] }>("/api/system/mode"),
  testDesign: () => get<TestDesignResponse>("/api/system/tests/design"),
  astIntelligence: () => get<AstIntelligenceResponse>("/api/system/ast-intelligence"),
  codeGraphStatus: () => get<CodeGraphStatusResponse>("/api/codegraph/status"),
  codeGraphGraph: (params: { level?: string; root?: string; edge_kinds?: string; node_kinds?: string; limit?: number } = {}) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") search.set(key, String(value));
    }
    const query = search.toString();
    return get<CodeGraphGraphResponse>(`/api/codegraph/graph${query ? `?${query}` : ""}`);
  },
  codeGraphSearch: (q: string, limit = 20) =>
    get<{ items: CodeGraphNode[] }>(`/api/codegraph/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  codeGraphNeighborhood: (nodeId: string, depth = 1, limit = 180) =>
    get<CodeGraphGraphResponse>(`/api/codegraph/neighborhood?node_id=${encodeURIComponent(nodeId)}&depth=${depth}&limit=${limit}`),
  codeGraphDiagnostics: (params: { scope?: string; root?: string; limit?: number; include_git?: boolean } = {}) => {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== "") search.set(key, String(value));
    }
    const query = search.toString();
    return get<CodeGraphDiagnosticsResponse>(`/api/codegraph/diagnostics${query ? `?${query}` : ""}`);
  },
  codeGraphSync: (mode: "sync" | "rebuild") => post<{ status: string; mode: string; results: any[] }>("/api/codegraph/sync", { mode }),
};
