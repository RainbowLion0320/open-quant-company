import type { SectorCard } from "../api";

export function signalPower(sector: SectorCard): number {
  const ratios = Object.values(sector.signals || {}).map(signal => Number(signal.buy_ratio || 0));
  return ratios.length ? Math.max(...ratios) : 0;
}

export function formatAmount(value: number): string {
  const n = Number(value || 0);
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}亿`;
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}万`;
  return n.toFixed(0);
}

export function dataSourceLabel(source: string): string {
  if (source === "real") return "真实数据";
  if (source === "proxy") return "代理数据";
  if (source === "estimated") return "估算数据";
  return "数据缺失";
}

export function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
