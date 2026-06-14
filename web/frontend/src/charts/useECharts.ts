/**
 * Open Quant Company Console — ECharts Composable
 *
 * Single shared wrapper for all ECharts instances across the app.
 * ECharts is dynamically imported — only loaded when a chart is first rendered.
 */
import { ref, onUnmounted, type Ref } from "vue";

let _echarts: any = null;
const _chartInitTasks = new WeakMap<HTMLElement, Promise<any>>();

export async function getECharts() {
  if (!_echarts) {
    const mod = await import("echarts");
    _echarts = mod;
  }
  return _echarts;
}

export function useECharts(elRef: Ref<HTMLElement | null>) {
  const instance = ref<any>(null);
  let resizeObserver: ResizeObserver | null = null;
  let initTask: Promise<void> | null = null;
  let pendingOption: { option: Record<string, any>; replace: boolean } | null = null;

  async function init() {
    const el = elRef.value;
    if (!el || instance.value) return initTask || Promise.resolve();
    if (initTask) return initTask;

    initTask = (async () => {
      const echarts = await getECharts();
      const currentEl = elRef.value;
      if (!currentEl || instance.value) return;

      let chart = echarts.getInstanceByDom?.(currentEl);
      if (!chart) {
        const sharedTask = _chartInitTasks.get(currentEl);
        if (sharedTask) {
          chart = await sharedTask;
        } else {
          const task = Promise.resolve().then(() => {
            const existing = echarts.getInstanceByDom?.(currentEl);
            if (existing) return existing;
            if (currentEl.getAttribute("_echarts_instance_")) {
              currentEl.removeAttribute("_echarts_instance_");
              currentEl.innerHTML = "";
            }
            return echarts.init(currentEl, undefined, {});
          });
          _chartInitTasks.set(currentEl, task);
          try {
            chart = await task;
          } finally {
            _chartInitTasks.delete(currentEl);
          }
        }
      }
      instance.value = chart;

      if (!resizeObserver && typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(() => {
          instance.value?.resize();
        });
        resizeObserver.observe(currentEl);
      }

      if (pendingOption) {
        instance.value?.setOption(pendingOption.option, { notMerge: pendingOption.replace });
        pendingOption = null;
      }
    })().finally(() => {
      initTask = null;
    });

    return initTask;
  }

  function setOption(option: Record<string, any>, replace = true) {
    if (!instance.value) {
      pendingOption = { option, replace };
      void init();
      return;
    }
    instance.value.setOption(option, { notMerge: replace });
  }

  function dispose() {
    resizeObserver?.disconnect();
    resizeObserver = null;
    instance.value?.dispose();
    instance.value = null;
  }

  onUnmounted(() => dispose());

  return { instance, init, setOption, dispose };
}

/**
 * Open Quant Company Console ECharts theme defaults.
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

export { fmtSignedRatioPct as fmtReturn, fmtConfigRatio as fmtPct } from "../utils/format";
