import { get, post } from "../client";
import type { PortfolioBalance, PortfolioNavPoint, PortfolioPosition, PortfolioSummary, PortfolioTrade } from "../types";

export const portfolioApi = {
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
};
