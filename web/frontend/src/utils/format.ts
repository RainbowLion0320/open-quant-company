export function isBlankNumber(v: number | null | undefined): boolean {
  return v == null || Number.isNaN(Number(v));
}

export function fmtRatioPct(v: number | null | undefined, digits = 2): string {
  if (isBlankNumber(v)) return "—";
  return `${(Number(v) * 100).toFixed(digits)}%`;
}

export function fmtSignedRatioPct(v: number | null | undefined, digits = 2): string {
  if (isBlankNumber(v)) return "—";
  const n = Number(v) * 100;
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

export function fmtPercentValue(v: number | null | undefined, digits = 1): string {
  if (isBlankNumber(v)) return "—%";
  return `${Number(v).toFixed(digits)}%`;
}

export function fmtFixedNumber(v: number | null | undefined, digits = 2): string {
  return isBlankNumber(v) ? "—" : Number(v).toFixed(digits);
}

export function fmtSignedPercentValue(v: number | null | undefined, digits = 2): string {
  if (isBlankNumber(v)) return "—";
  const n = Number(v);
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

export function fmtConfigRatio(v: number | null | undefined, digits = 0): string {
  if (isBlankNumber(v)) return "—";
  return `${(Number(v) * 100).toFixed(digits)}%`;
}

export function colorBySignedRatio(v: number | null | undefined, threshold = 0.005): string {
  const n = Number(v || 0);
  if (n > threshold) return "var(--positive)";
  if (n < -threshold) return "var(--negative)";
  return "var(--text-secondary)";
}

export function fmtShortCount(n: number | null | undefined): string {
  if (isBlankNumber(n)) return "—";
  const value = Number(n);
  if (value > 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value > 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(Math.round(value));
}
