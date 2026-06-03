import type { KlinePoint } from "./market";
import type { StrategySignal } from "./strategy";

export interface StockDetail {
  basic: { symbol: string; name: string; industry: string; sector: string; area: string; market: string };
  buffett?: { score: number; roe: number; gross_margin: number; debt_equity: number; dcf_value: number };
  kline?: KlinePoint[];
  signals?: Record<string, StrategySignal[]>;
  financials?: any[];
}

export interface StockListItem {
  symbol: string;
  name: string;
  industry: string;
  sector: string;
  price: number | null;
  change_pct: number | null;
  pe_ttm: number | null;
  pb: number | null;
  total_mv: number | null;
  buffett_score: number | null;
  roe: number | null;
  gross_margin: number | null;
  signal_score: number | null;
  signal: "buy" | "hold" | string;
  buy_signals: number;
  signal_count: number;
  top_strategy: string;
  updated_at: string;
}

export interface StockListResponse {
  stocks: StockListItem[];
  total: number;
  limit: number;
  updated_at: string;
}
