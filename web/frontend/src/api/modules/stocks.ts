import { get } from "../client";
import type { SignalChange, StockDetail, StockListResponse, StrategySignal } from "../types";

function pct(v: unknown): number | undefined {
  if (v == null) return undefined;
  const n = Number(v);
  if (!Number.isFinite(n)) return undefined;
  return Math.abs(n) > 1 ? n / 100 : n;
}

export const stocksApi = {
  stockList: (limit = 300) => get<StockListResponse>(`/api/stocks?limit=${limit}`),
  stock: async (code: string) => {
    const data = await get<any>(`/api/stocks/${encodeURIComponent(code)}`);
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
};
