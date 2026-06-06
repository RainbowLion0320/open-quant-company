import { get, post } from "../client";
import type { DbHealthResponse, DbRepairResponse, HindsightGraphResponse, LlmUsageResponse, SystemHistoryResponse, SystemMonitor } from "../types";

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
  hindsightGraph: () => get<HindsightGraphResponse>("/api/hindsight/graph"),
};
