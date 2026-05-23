/**
 * Quantum Terminal — Shared API Client
 *
 * Every API call goes through here. No raw fetch() scattered across views.
 * Auto error handling, type-safe return values.
 * Auth: reads api_key from localStorage, attaches Bearer token.
 */

const BASE = ""; // Vite proxy handles /api → localhost:8501

function authHeaders(): Record<string, string> {
  const key = localStorage.getItem("quant_api_key");
  return key ? { Authorization: `Bearer ${key}` } : {};
}

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + url, {
    headers: { "Content-Type": "application/json", ...authHeaders(), ...opts?.headers },
    ...opts,
  });
  const contentType = res.headers.get("content-type") || "";
  const text = await res.text().catch(() => "");
  if (!res.ok) {
    if (res.status === 401 || (res.status === 403 && /Invalid API key/i.test(text))) {
      localStorage.removeItem("quant_api_key"); // clear stale key only on auth failure
    }
    throw new Error(`[${res.status}] ${text || "Unknown error"}`);
  }
  if (!contentType.includes("application/json")) {
    const hint = contentType.includes("text/html")
      ? "后端路由可能未注册，或本地 API 服务需要重启"
      : "接口未返回 JSON";
    throw new Error(`${hint}: ${url}`);
  }
  return JSON.parse(text) as T;
}

/** GET request */
function get<T>(url: string): Promise<T> {
  return req<T>(url);
}

/** POST request */
function post<T>(url: string, body?: unknown): Promise<T> {
  return req<T>(url, { method: "POST", body: body ? JSON.stringify(body) : undefined });
}

/** PUT request */
function put<T>(url: string, body?: unknown): Promise<T> {
  return req<T>(url, { method: "PUT", body: body ? JSON.stringify(body) : undefined });
}

// ═══════════════════════════════════════
// Type definitions
// ═══════════════════════════════════════

export interface RegimeData {
  value: "bull" | "bear" | "sideways";
  ma_trend: string;
  volume_trend: string;
  breadth: number;
}

export interface KlinePoint {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
}

export interface StrategyMeta {
  name: string;
  label: string;
  color: string;
  enabled: boolean;
}

export interface MarketSeriesPoint {
  date: string;
  value: number;
}

export interface MarketAssetCard {
  key: string;
  label: string;
  symbol: string;
  value: number | null;
  change: number;
  change_pct: number;
  unit: string;
  series: MarketSeriesPoint[];
  data_source: string;       // "real" | "proxy" | "placeholder" | "cached" | "missing"
  source_detail?: string;    // human-readable detail
}

export interface MacroCard {
  key: string;
  label: string;
  value: number | null;
  prev: number | null;
  unit: string;
  date: string;
  series: MarketSeriesPoint[];
}

export interface MarketAlert {
  level: "success" | "warning" | "danger" | "info";
  title: string;
  detail: string;
  time: string;
}

export interface MarketResponse {
  regime: RegimeData;
  kline: KlinePoint[];
  range?: string;
  multi_asset?: MarketAssetCard[];
  macro?: MacroCard[];
  freshness?: { market: string; macro: string };
  pool_size?: number;
  updated?: string;
}

export interface RegimeResponse {
  regime: RegimeData & { score?: number };
  multi_asset: MarketAssetCard[];
  freshness: { market: string };
  updated: string;
  config?: Record<string, any>;
}

export interface StrategySignal {
  strategy?: string;
  symbol: string;
  name: string;
  industry: string;
  score: number;
  signal: "buy" | "hold";
  detail?: any;
  computed_at?: string;
}

export interface StrategyInfo {
  name: string;
  label: string;
  total: number;
  buys: number;
  last_computed: string;
}

export interface StrategiesResponse {
  strategies: StrategyInfo[];
  registry?: StrategyMeta[];
  total?: number;
  statuses?: string[];
}

export interface StrategyStatusItem {
  name: string;
  label: string;
  status: string;
  status_label: string;
  color: string;
}

export interface StrategyStatusesResponse {
  strategies: StrategyStatusItem[];
  statuses: string[];
  status_labels: Record<string, string>;
  status: string;
}

export interface StrategyDetailResponse {
  signals: StrategySignal[];
}

export interface RunResponse {
  job_id: string;
}

export interface EquityPoint {
  date: string;
  value: number;
}

export interface BacktestOverview {
  start: string;
  end: string;
  bench_return: number;
  strategies: Record<string, {
    total_return: number;
    sharpe: number;
    max_drawdown: number;
    win_rate: number;
    trade_count: number;
  }>;
}

export interface BacktestDetail {
  equity_curve: EquityPoint[];
  bench_curve: EquityPoint[];
}

export interface PortfolioPosition {
  symbol: string;
  name: string;
  shares: number;
  cost: number;
  price: number;
  pnl: number;
  pnl_pct: number;
}

export interface PortfolioBalance {
  cash: number;
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
}

export interface PortfolioNavPoint {
  date: string;
  total_asset: number;
  cash: number;
  market_value: number;
}

export interface PortfolioTrade {
  date: string;
  code: string;
  name: string;
  side: "buy" | "sell";
  price: number;
  volume: number;
  amount: number;
  strategy: string;
}

export interface PortfolioSummary {
  balance?: { total_asset: number; cash: number; market_value: number };
  total_return: number;
  total_return_pct: number;
  positions_count: number;
  position_value: number;
  peak_equity: number;
  nav_days: number;
}

export interface StockDetail {
  basic: { symbol: string; name: string; industry: string; sector: string; area: string; market: string };
  buffett?: { score: number; roe: number; gross_margin: number; debt_equity: number; dcf_value: number };
  kline?: KlinePoint[];
  signals?: Record<string, StrategySignal[]>;
  financials?: any[];
}

export interface SignalChange {
  date: string;
  strategy: string;
  symbol: string;
  name: string;
  old_signal: string;
  new_signal: string;
}

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
  status?: string;
  message?: string;
}

export interface SectorSignal {
  total: number;
  buy_count: number;
  buy_ratio: number;
  avg_score: number;
  top_symbol: string;
}

export interface SectorCard {
  sector_code: string;
  sector_name: string;
  rank: number;
  return_1d: number;
  return_5d: number;
  return_20d: number;
  return_60d: number;
  volatility: number;
  member_count: number;
  data_source: string;
  signals: Record<string, SectorSignal>;
}

export interface SectorOverviewResponse {
  sectors: SectorCard[];
  total_sectors: number;
  top_performers: SectorCard[];
  bottom_performers: SectorCard[];
  signal_concentration: number;
  data_source: string;
  freshness: { performance: string; signals: string };
}

export interface SectorExposureItem {
  sector: string;
  date: string;
  weight: number;
  market_value: number;
  position_count: number;
}

export interface SectorExposureResponse {
  exposure: SectorExposureItem[];
  total_sectors: number;
  data_source: string;
}

export interface SectorDetailResponse {
  sector_name: string;
  performance: Record<string, any>;
  signals: Record<string, SectorSignal>;
  data_source: string;
}

export interface SectorStock {
  symbol: string;
}

export interface SectorStocksResponse {
  industry: string;
  stocks: SectorStock[];
  total: number;
  data_source: string;
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

function pct(v: unknown): number | undefined {
  if (v == null) return undefined;
  const n = Number(v);
  if (!Number.isFinite(n)) return undefined;
  return Math.abs(n) > 1 ? n / 100 : n;
}

// ═══════════════════════════════════════
// API functions
// ═══════════════════════════════════════

export const api = {
  // Market
  market: (range = "6M") => get<MarketResponse>(`/api/market?range=${encodeURIComponent(range)}`),
  marketRegime: () => get<RegimeResponse>("/api/market/regime"),

  // Strategies
  strategies: () => get<StrategiesResponse>("/api/strategies"),
  strategyStatuses: () => get<StrategyStatusesResponse>("/api/strategies/statuses"),
  strategyDetail: (name: string) => get<StrategyDetailResponse>(`/api/strategies/${name}`),
  strategyRun: (strategy: string, limit = 0, params?: any) =>
    post<RunResponse>("/api/strategies/run", { strategy, limit, params }),

  // Backtest
  backtest: () => get<BacktestOverview>("/api/backtest"),
  backtestDetail: (key: string) => get<BacktestDetail>(`/api/backtest/${key}`),

  // Portfolio
  portfolioPositionRows: () => get<{ positions: any[] }>("/api/portfolio/positions"),
  portfolioPositions: async () => {
    const data = await get<{ positions: any[] }>("/api/portfolio/positions");
    return (data.positions || []).map((p) => ({
      symbol: p.code,
      name: p.name,
      shares: p.volume,
      cost: p.avg_cost,
      price: p.current_price,
      pnl: p.pnl,
      pnl_pct: (p.pnl_pct || 0) / 100,
    })) as PortfolioPosition[];
  },
  portfolioBalance: async () => {
    const data = await get<any>("/api/portfolio/balance");
    const initial = 1_000_000;
    const total = Number(data.total_asset || 0);
    const pnl = total - initial;
    return {
      cash: Number(data.cash || 0),
      total_value: total,
      total_pnl: pnl,
      total_pnl_pct: initial > 0 ? pnl / initial : 0,
    } as PortfolioBalance;
  },
  portfolioOrder: (order: { symbol: string; side: "buy" | "sell"; shares: number; price?: number }) =>
    post<any>("/api/portfolio/order", {
      code: order.symbol,
      side: order.side,
      volume: order.shares,
      price: order.price ?? 0,
    }),
  portfolioNav: () => get<{ nav: PortfolioNavPoint[] }>("/api/portfolio/nav"),
  portfolioTrades: (limit = 50) => get<{ trades: PortfolioTrade[]; total: number }>(`/api/portfolio/trades?limit=${limit}`),
  portfolioSummary: () => get<PortfolioSummary>("/api/portfolio/summary"),
  portfolioRefresh: () => post<any>("/api/portfolio/refresh"),
  portfolioSectorExposure: () => get<SectorExposureResponse>("/api/portfolio/sector-exposure"),

  // Stocks
  stock: async (code: string) => {
    const data = await get<any>(`/api/stocks/${code}`);
    const br = data.buffett_result || null;
    const grouped: Record<string, StrategySignal[]> = {};
    for (const sig of data.signals || []) {
      const key = sig.strategy || "strategy";
      (grouped[key] ||= []).push(sig);
    }
    return {
      ...data,
      basic: {
        ...data.basic,
        area: data.basic?.area || "",
        market: data.basic?.market || "",
      },
      buffett: br ? {
        score: Number(br.score || 0),
        roe: pct(br.avg_roe_5y) ?? 0,
        gross_margin: pct(br.avg_gross_margin_5y) ?? pct(br.avg_net_margin_5y) ?? 0,
        debt_equity: Number(br.debt_equity_ratio || 0),
        dcf_value: Number(br.dcf_value || 0),
      } : undefined,
      signals: grouped,
    } as StockDetail;
  },

  // Signals
  signalChanges: async (days = 7) => {
    const data = await get<any>(`/api/signals/changes?days=${days}`);
    return (data.changes || []).map((c: any) => ({
      date: c.date,
      strategy: c.strategy,
      symbol: c.symbol,
      name: c.name,
      old_signal: c.from_signal,
      new_signal: c.to_signal,
    })) as SignalChange[];
  },

  // System Monitor
  systemMonitor: () => get<SystemMonitor>("/api/system/monitor"),
  systemHistory: (hours = 24) => get<SystemHistoryResponse>(`/api/system/history?hours=${hours}`),
  deepseekUsage: () => get<DeepSeekUsageResponse>("/api/system/deepseek-usage"),

  // System Monitor
  apiHealth: () => get<{ items: { name: string; status: string; detail: string; cookie_remaining_days?: number }[]; summary: string; all_ok: boolean }>("/api/system/api-health"),
  cronJobs: () => get<{ jobs: { name: string; schedule: string; last_run: string | null; last_status: string | null; next_run: string | null; enabled: boolean; state: string; no_agent: boolean }[]; summary: string }>("/api/system/cron-jobs"),
  serviceStatus: () => get<{ items: { name: string; status: string; detail: string; cookie_remaining_days?: number }[]; summary: string; all_ok: boolean }>("/api/system/service-status"),
  dbHealth: () => get<DbHealthResponse>("/api/system/db-health"),
  dbHealthRepair: (table: string) => post<DbRepairResponse>(`/api/system/db-health/repair/${encodeURIComponent(table)}`),
  dbHealthRepairStatus: (jobId: string) => get<DbRepairResponse>(`/api/system/db-health/repair-status/${encodeURIComponent(jobId)}`),

  // Settings
  settings: async () => {
    const data = await get<any>("/api/settings");
    return data.config || {};
  },
  saveSettings: (data: Record<string, any>) => put<Record<string, any>>("/api/settings", data),

  // Sectors
  sectorOverview: () => get<SectorOverviewResponse>("/api/sectors/overview"),
  sectorExposure: () => get<SectorExposureResponse>("/api/sectors/exposure"),
  sectorDetail: (industry: string) => get<SectorDetailResponse>(`/api/sectors/${encodeURIComponent(industry)}`),
  sectorStocks: (industry: string) => get<SectorStocksResponse>(`/api/sectors/${encodeURIComponent(industry)}/stocks`),

  // Audit & Run Mode
  auditHistory: (section = "", limit = 50) =>
    get<{ entries: any[]; summary: any; total: number }>(`/api/system/audit?section=${encodeURIComponent(section)}&limit=${limit}`),
  systemMode: () => get<{ mode: string; has_api_key: boolean; allows_settings_write: boolean; allows_paper_trading: boolean; readonly_sections: string[] }>("/api/system/mode"),
  hindsightGraph: () => get<HindsightGraphResponse>("/api/hindsight/graph"),
};
