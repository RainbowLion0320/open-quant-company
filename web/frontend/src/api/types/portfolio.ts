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
