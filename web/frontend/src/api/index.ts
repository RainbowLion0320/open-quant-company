/**
 * Quantum Terminal — Shared API Client
 *
 * Every API call goes through here. No raw fetch() scattered across views.
 * Auto error handling, type-safe return values.
 */

const BASE = ""; // Vite proxy handles /api → localhost:8501

async function req<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(BASE + url, {
    headers: { "Content-Type": "application/json", ...opts?.headers },
    ...opts,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`[${res.status}] ${text}`);
  }
  return res.json();
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

export interface MarketResponse {
  regime: RegimeData;
  kline: KlinePoint[];
  config: Record<string, any>;
  registry: StrategyMeta[];
}

export interface StrategySignal {
  symbol: string;
  name: string;
  industry: string;
  score: number;
  signal: "buy" | "hold";
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

export interface StockDetail {
  basic: { symbol: string; name: string; industry: string; area: string; market: string };
  buffet?: { score: number; roe: number; gross_margin: number; debt_equity: number; dcf_value: number };
  kline?: KlinePoint[];
  signals?: Record<string, StrategySignal[]>;
}

export interface SignalChange {
  date: string;
  strategy: string;
  symbol: string;
  name: string;
  old_signal: string;
  new_signal: string;
}

// ═══════════════════════════════════════
// API functions
// ═══════════════════════════════════════

export const api = {
  // Market
  market: () => get<MarketResponse>("/api/market"),

  // Strategies
  strategies: () => get<StrategiesResponse>("/api/strategies"),
  strategyDetail: (name: string) => get<StrategyDetailResponse>(`/api/strategies/${name}`),
  strategyRun: (strategy: string, limit = 0, params?: any) =>
    post<RunResponse>("/api/strategies/run", { strategy, limit, params }),

  // Backtest
  backtest: () => get<BacktestOverview>("/api/backtest"),
  backtestDetail: (key: string) => get<BacktestDetail>(`/api/backtest/${key}`),

  // Portfolio
  portfolioPositions: () => get<PortfolioPosition[]>("/api/portfolio/positions"),
  portfolioBalance: () => get<PortfolioBalance>("/api/portfolio/balance"),
  portfolioOrder: (order: { symbol: string; side: "buy" | "sell"; shares: number; price?: number }) =>
    post<any>("/api/portfolio/order", order),

  // Stocks
  stock: (code: string) => get<StockDetail>(`/api/stocks/${code}`),

  // Signals
  signalChanges: (days = 7) => get<SignalChange[]>(`/api/signals/changes?days=${days}`),

  // Settings
  settings: () => get<Record<string, any>>("/api/settings"),
  saveSettings: (data: Record<string, any>) => put<Record<string, any>>("/api/settings", data),
};
