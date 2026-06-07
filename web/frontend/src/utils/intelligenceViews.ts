export function topModule(path: string) {
  return path.split("/", 1)[0] || path;
}

export function formatArtifactDate(value: string, locale: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale);
}

export function heatCellStyle(
  value: number,
  maxValue: number,
  rgb: string,
  alpha: { backgroundBase: number; backgroundScale: number; borderBase: number; borderScale: number },
) {
  const intensity = value / Math.max(1, maxValue);
  return {
    backgroundColor: `rgba(${rgb}, ${alpha.backgroundBase + intensity * alpha.backgroundScale})`,
    borderColor: `rgba(${rgb}, ${alpha.borderBase + intensity * alpha.borderScale})`,
  };
}
