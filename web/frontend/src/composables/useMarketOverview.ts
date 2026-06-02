export interface MarketTimeRange {
  key: string;
  label: string;
}

export function useMarketOverview() {
  const timeRanges: MarketTimeRange[] = [
    { key: "1D", label: "1D" },
    { key: "1M", label: "1M" },
    { key: "6M", label: "6M" },
    { key: "YTD", label: "YTD" },
  ];

  const indexColors: Record<string, string> = {
    sse: "#7dd3fc",
    csi300: "#22c55e",
    chinext: "#f59e0b",
    star50: "#a78bfa",
  };

  return { timeRanges, indexColors };
}
