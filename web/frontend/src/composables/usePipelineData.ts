export function formatPipelineParam(key: string, value: string | number) {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value ?? "-");
  if (key === "position_size" || key === "stop_loss" || key === "confidence_threshold") {
    return `${(n * 100).toFixed(1)}%`;
  }
  return `${Math.round(n)}`;
}

export function regimeClass(regime: string) {
  const v = String(regime || "").toLowerCase();
  if (v === "bull") return "positive";
  if (v === "bear") return "negative";
  if (v === "sideways") return "warning";
  return "neutral";
}

export function metricClass(tone?: string) {
  return tone || "neutral";
}
