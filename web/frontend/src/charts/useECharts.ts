/**
 * Quantum Terminal — ECharts Composable
 *
 * Single shared wrapper for all ECharts instances across the app.
 * No more scattered init/dispose — one composable, one pattern.
 */
import { ref, onMounted, onUnmounted, watch, type Ref } from "vue";
import * as echarts from "echarts";

export interface ChartOptions {
  /** ECharts option object */
  option: echarts.EChartsOption;
  /** Whether to notMerge (default: true — replaces entire option) */
  replace?: boolean;
}

export function useECharts(elRef: Ref<HTMLElement | null>) {
  const instance = ref<echarts.ECharts | null>(null);
  let resizeObserver: ResizeObserver | null = null;

  function init() {
    const el = elRef.value;
    if (!el || instance.value) return;

    instance.value = echarts.init(el, undefined, {
      // Custom dark theme inline
    });

    resizeObserver = new ResizeObserver(() => {
      instance.value?.resize();
    });
    resizeObserver.observe(el);
  }

  function setOption(option: echarts.EChartsOption, replace = true) {
    instance.value?.setOption(option, { notMerge: replace });
  }

  function dispose() {
    resizeObserver?.disconnect();
    instance.value?.dispose();
    instance.value = null;
  }

  onMounted(() => {
    // init called explicitly by consumer when ready
  });

  onUnmounted(() => dispose());

  return { instance, init, setOption, dispose };
}

/**
 * Quantum terminal ECharts theme defaults.
 * Apply these to every chart via setOption + spread.
 */
export const QUANTUM_THEME = {
  backgroundColor: "transparent",
  textStyle: {
    color: "#64748b",
    fontSize: 10,
  },
  tooltip: {
    trigger: "axis" as const,
    backgroundColor: "rgba(10, 17, 32, 0.95)",
    borderColor: "rgba(255,255,255,0.06)",
    textStyle: { color: "#e2e8f0", fontSize: 11 },
    axisPointer: {
      type: "cross" as const,
      lineStyle: { color: "rgba(255,255,255,0.06)" },
    },
  },
  grid: {
    left: 8,
    right: 8,
    top: 8,
    bottom: 8,
    containLabel: true,
  },
  xAxis: {
    axisLine: { lineStyle: { color: "rgba(255,255,255,0.04)" } },
    axisTick: { show: false },
    axisLabel: { color: "#475569", fontSize: 9 },
    splitLine: { show: false },
  },
  yAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: "#475569", fontSize: 9 },
    splitLine: { lineStyle: { color: "rgba(255,255,255,0.04)" } },
  },
};

/**
 * Format a decimal return to percentage string.
 * e.g. 0.2831 → "+28.31%"
 */
export function fmtReturn(v: number): string {
  return (v >= 0 ? "+" : "") + (v * 100).toFixed(2) + "%";
}

/**
 * Format a decimal to percentage string.
 * e.g. 0.15 → "15%"
 */
export function fmtPct(v: number): string {
  return v.toFixed(0) + "%";
}
