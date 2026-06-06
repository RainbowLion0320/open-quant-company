import { computed, type ComputedRef, type Ref } from "vue";
import type { MarketAssetCard } from "../api";

export interface RelativeLine {
  key: string;
  label: string;
  color: string;
  change: number;
  data: Array<number | null>;
  data_source?: string;
  source_detail?: string;
}

const CHART_VIEW_W = 720;
const CHART_VIEW_H = 310;
const CHART_LEFT = 44;
const CHART_RIGHT = 702;
const CHART_TOP = 34;
const CHART_BOTTOM = 282;
const CHART_WIDTH = CHART_RIGHT - CHART_LEFT;
const CHART_HEIGHT = CHART_BOTTOM - CHART_TOP;

export function useRelativeStrengthChart(
  assets: ComputedRef<MarketAssetCard[]>,
  indexColors: Record<string, string>,
  waitingLabel: () => string,
  freshness: Ref<string>,
) {
  const relativeChart = computed(() => {
    const cards = (assets.value || []).filter((asset: MarketAssetCard) => (asset.series || []).length >= 2);
    const dates = Array.from(new Set(cards.flatMap((asset: MarketAssetCard) => (asset.series || []).map(point => point.date)))).sort();
    const lines: RelativeLine[] = cards.map((asset: MarketAssetCard) => {
      const points = (asset.series || [])
        .map(point => ({ date: point.date, value: Number(point.value) }))
        .filter(point => point.date && Number.isFinite(point.value))
        .sort((a, b) => a.date.localeCompare(b.date));
      const base = points.find(point => point.value !== 0)?.value || 0;
      const values = new Map(points.map(point => [point.date, point.value]));
      const data = dates.map(date => {
        const value = values.get(date);
        if (!base || value == null || !Number.isFinite(value)) return null;
        return Number((((value / base) - 1) * 100).toFixed(2));
      });
      const finite = data.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
      return {
        key: asset.key,
        label: asset.label,
        color: indexColors[asset.key] || "#7dd3fc",
        change: finite.length ? finite[finite.length - 1] : 0,
        data,
        data_source: asset.data_source,
        source_detail: asset.source_detail,
      };
    }).filter(line => line.data.some(value => value != null));
    return { dates, lines };
  });

  const strengthLeader = computed(() => {
    const [leader] = [...relativeChart.value.lines].sort((a, b) => b.change - a.change);
    return leader || { key: "", label: "—", color: "var(--text-disabled)", change: 0, data: [] };
  });

  const relativeSubtitle = computed(() => {
    const dates = relativeChart.value.dates;
    const rangeText = dates.length ? `${dates[0]} -> ${dates[dates.length - 1]}` : waitingLabel();
    return `${rangeText} · ${freshness.value}`;
  });

  const chartScale = computed(() => {
    const values = relativeChart.value.lines
      .flatMap(line => line.data)
      .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
    if (!values.length) return { min: -1, max: 1 };
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const spread = rawMax - rawMin || 1;
    const pad = Math.max(spread * 0.12, 0.5);
    return { min: rawMin - pad, max: rawMax + pad };
  });

  const chartTicks = computed(() => {
    const { min, max } = chartScale.value;
    const step = (max - min) / 4;
    return Array.from({ length: 5 }, (_, index) => Number((max - step * index).toFixed(2)));
  });

  const chartXLabels = computed(() => {
    const dates = relativeChart.value.dates;
    if (!dates.length) return [];
    const indices = Array.from(new Set([0, Math.floor((dates.length - 1) / 2), dates.length - 1]));
    return indices.map(index => ({
      date: dates[index],
      label: shortDate(dates[index]),
      left: `${(chartX(index, dates.length) / CHART_VIEW_W) * 100}%`,
    }));
  });

  function chartX(index: number, total: number) {
    if (total <= 1) return CHART_LEFT;
    return CHART_LEFT + (index / (total - 1)) * CHART_WIDTH;
  }

  function chartY(value: number) {
    const { min, max } = chartScale.value;
    const spread = max - min || 1;
    return CHART_TOP + ((max - value) / spread) * CHART_HEIGHT;
  }

  function chartLabelTop(value: number) {
    return `${(chartY(value) / CHART_VIEW_H) * 100}%`;
  }

  function linePath(line: RelativeLine) {
    const total = relativeChart.value.dates.length;
    let started = false;
    return line.data.map((value, index) => {
      if (value == null || !Number.isFinite(value)) {
        started = false;
        return "";
      }
      const cmd = started ? "L" : "M";
      started = true;
      return `${cmd} ${chartX(index, total).toFixed(1)} ${chartY(value).toFixed(1)}`;
    }).filter(Boolean).join(" ");
  }

  return {
    CHART_VIEW_W,
    CHART_VIEW_H,
    CHART_LEFT,
    CHART_RIGHT,
    relativeChart,
    relativeSubtitle,
    strengthLeader,
    chartTicks,
    chartXLabels,
    chartY,
    chartLabelTop,
    linePath,
  };
}

function shortDate(date: string) {
  const match = date.match(/^\d{4}-(\d{2})-(\d{2})/);
  return match ? `${match[1]}-${match[2]}` : date;
}
