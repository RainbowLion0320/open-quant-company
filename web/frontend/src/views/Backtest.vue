<template>
  <div class="view-page">
    <!-- Header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">回测分析</h1>
        <p class="page-subtitle">{{ overview.start || '2015-01' }} → {{ overview.end || '2026-05' }} · 日频引擎 · 策略自主调仓</p>
      </div>
    </div>

    <!-- Per-strategy rows -->
    <div v-for="s in strategies" :key="s.key" class="glass-card glow-cyan animate-fade-in card-pad-lg">
      <div class="flex flex-col md:flex-row gap-6" style="min-height:220px">
        <!-- Left: Stats -->
        <div class="flex flex-col justify-center shrink-0 w-full md:w-[150px]">
          <!-- Strategy header -->
          <div class="flex items-center gap-2 mb-3">
            <div class="w-2 h-2 rounded-full" :style="{ background: s.color, boxShadow: `0 0 6px ${s.color}` }"></div>
            <div class="text-xs font-semibold tracking-wide" :style="{ color: s.color }">{{ s.label }}</div>
          </div>

          <!-- Return -->
          <div class="text-2xl font-bold font-mono mb-1" :class="s.data.total_return >= 0 ? 'text-[var(--positive)]' : 'text-[var(--negative)]'">
            {{ fmtReturn(s.data.total_return) }}
          </div>

          <!-- Stats grid -->
          <div class="grid grid-cols-2 gap-x-2 gap-y-1 mt-2">
            <div class="text-[10px]" style="color:var(--text-disabled)">Sharpe</div>
            <div class="text-[10px] font-mono text-right" style="color:var(--text-secondary)">{{ (s.data.sharpe||0).toFixed(2) }}</div>
            <div class="text-[10px]" style="color:var(--text-disabled)">最大回撤</div>
            <div class="text-[10px] font-mono text-right" :style="{ color: (s.data.max_drawdown||0) < -0.2 ? 'var(--negative)' : 'var(--text-secondary)' }">
              {{ fmtReturn(s.data.max_drawdown) }}
            </div>
            <div class="text-[10px]" style="color:var(--text-disabled)">胜率</div>
            <div class="text-[10px] font-mono text-right" style="color:var(--text-secondary)">{{ ((s.data.win_rate||0)*100).toFixed(0) }}%</div>
            <div class="text-[10px]" style="color:var(--text-disabled)">交易</div>
            <div class="text-[10px] font-mono text-right" style="color:var(--text-secondary)">{{ s.data.trade_count }}</div>
          </div>
        </div>

        <!-- Right: Chart -->
        <div :ref="el => setChartRef(s.key, el as HTMLElement)" style="flex:1; min-height:200px"></div>
      </div>
    </div>

    <div v-if="loaded && !strategies.length" class="glass-card card-pad-lg empty-panel">
      暂无回测结果
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import { api } from "../api";
import { fmtReturn, QUANTUM_THEME } from "../charts/useECharts";

let echarts: any = null;
async function getECharts() {
  if (!echarts) echarts = await import("echarts");
  return echarts;
}

const overview = ref<any>({});
const strategyList = ref<Array<{ key: string; label: string; color: string }>>([]);
const loaded = ref(false);

const strategies = computed(() =>
  strategyList.value.map(s => ({
    ...s,
    data: overview.value.strategies?.[s.key] || {},
  }))
);

const allCurves = ref<Record<string, { equity: any[]; bench: any[] }>>({});

// Multi-chart management
const chartRefs: Record<string, HTMLElement> = {};
const charts: Record<string, any> = {};

function setChartRef(key: string, el: HTMLElement | null) {
  if (el) chartRefs[key] = el;
}

async function loadAllDetails() {
  const results: Record<string, { equity: any[]; bench: any[] }> = {};
  await Promise.all(strategyList.value.map(async s => {
    try {
      const d = await api.backtestDetail(s.key);
      results[s.key] = { equity: d.equity_curve || [], bench: d.bench_curve || [] };
    } catch {}
  }));
  allCurves.value = results;
  setTimeout(() => initAllCharts(), 50);
}

async function initAllCharts() {
  const ec = await getECharts();
  for (const s of strategyList.value) {
    const el = chartRefs[s.key];
    if (!el) continue;
    const curve = allCurves.value[s.key];
    if (!curve?.equity?.length) continue;

    if (charts[s.key]) charts[s.key].dispose();

    const chart = ec.init(el);
    charts[s.key] = chart;

    const dates = curve.equity.map((d: any) => d.date);
    const values = curve.equity.map((d: any) => d.value);

    const series: any[] = [{
      name: s.label,
      type: "line",
      data: values,
      lineStyle: { color: s.color, width: 1.5 },
      itemStyle: { color: s.color },
      symbol: "none",
      smooth: true,
      areaStyle: {
        color: new ec.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: s.color + "20" },
          { offset: 1, color: "rgba(0,0,0,0)" },
        ]),
      },
    }];

    if (curve.bench?.length) {
      series.push({
        name: "上证指数",
        type: "line",
        data: curve.bench.map((d: any) => d.value),
        lineStyle: { color: "rgba(255,255,255,0.08)", width: 1, type: "dashed" },
        itemStyle: { color: "rgba(255,255,255,0.08)" },
        symbol: "none",
      });
    }

    chart.setOption({
      ...QUANTUM_THEME,
      tooltip: {
        ...QUANTUM_THEME.tooltip,
        trigger: "axis",
      },
      grid: { left: 50, right: 12, top: 30, bottom: 20 },
      xAxis: {
        type: "category", data: dates,
        axisLabel: { show: false },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.04)" } },
      },
      yAxis: {
        type: "value",
        axisLabel: { fontSize: 9, color: "#64748b" },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.03)" } },
      },
      legend: {
        data: [s.label, "上证指数"],
        textStyle: { color: "#64748b", fontSize: 10 },
        top: 0, right: 0,
      },
      series,
    });
  }
}

onMounted(async () => {
  try {
    const regData = await api.strategies();
    if (regData.registry?.length) {
      strategyList.value = regData.registry.map((r: any) => ({
        key: r.name, label: r.label, color: r.color
      }));
    }
    overview.value = await api.backtest();
    if (!strategyList.value.length) {
      strategyList.value = Object.keys(overview.value.strategies || {}).map(k => ({
        key: k, label: k, color: "#00d4ff"
      }));
    }
    await loadAllDetails();
  } catch {
    strategyList.value = [];
    overview.value = {};
  } finally {
    loaded.value = true;
  }
});

onUnmounted(() => {
  Object.values(charts).forEach(c => c.dispose());
});
</script>

<style scoped>
.empty-panel {
  min-height: 140px;
  display: grid;
  place-items: center;
  color: var(--text-disabled);
  font-size: 12px;
}
</style>
