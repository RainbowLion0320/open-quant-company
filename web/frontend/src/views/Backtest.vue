<template>
  <div class="p-5 space-y-5">
    <!-- 顶栏 -->
    <div class="flex items-center justify-between">
      <h1 class="text-sm font-semibold tracking-wide" style="color:var(--text-primary)">回测分析</h1>
      <span class="text-xs" style="color:var(--text-quaternary)">{{ overview.start || '2015-01' }} ~ {{ overview.end || '2026-05' }} · 月度调仓 · 100只</span>
    </div>

    <!-- 策略 × 行：左统计 + 右图表 -->
    <div v-for="s in strategies" :key="s.key" class="card p-4">
      <div class="flex gap-5 items-stretch" style="min-height:220px">
        <!-- 左侧统计摘要 -->
        <div class="flex flex-col justify-center" style="min-width:140px; max-width:160px">
          <div class="text-xs font-semibold tracking-wide mb-3" :style="{ color: s.color }">{{ s.label }}</div>
          <div class="text-lg font-semibold font-mono mb-2" :class="s.data.total_return >= 0 ? 'text-[var(--green)]' : 'text-[var(--red)]'">{{ fmt(s.data.total_return) }}</div>
          <div class="space-y-1 text-[11px]" style="color:var(--text-quaternary)">
            <div>Sharpe: <span class="tabular-nums" style="color:var(--text-secondary)">{{ (s.data.sharpe||0).toFixed(2) }}</span></div>
            <div>回撤: <span class="tabular-nums" style="color:var(--text-secondary)">{{ fmt(s.data.max_drawdown) }}</span></div>
            <div>胜率: <span class="tabular-nums" style="color:var(--text-secondary)">{{ ((s.data.win_rate||0)*100).toFixed(0) }}%</span></div>
            <div>交易: <span class="tabular-nums" style="color:var(--text-secondary)">{{ s.data.trade_count }} 笔</span></div>
          </div>
        </div>
        <!-- 右侧图表 -->
        <div :ref="el => setChartRef(s.key, el)" style="flex:1; min-height:200px"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import * as echarts from "echarts";

const overview = ref<any>({});
const benchReturn = computed(() => overview.value.bench_return || 0);

const strategyList = ref<Array<{ key: string; label: string; color: string }>>([]);
const strategies = computed(() => strategyList.value.map(s => ({
  ...s,
  data: overview.value.strategies?.[s.key] || {},
})));

const allCurves = ref<Record<string, { equity: any[]; bench: any[] }>>({});

// 多图表管理
const chartRefs: Record<string, HTMLDivElement> = {};
const charts: Record<string, echarts.ECharts> = {};

function setChartRef(key: string, el: any) {
  if (el) chartRefs[key] = el;
}

function fmt(v: number) { return (v >= 0 ? "+" : "") + (v * 100).toFixed(2) + "%"; }

async function loadAllDetails() {
  const results: Record<string, { equity: any[]; bench: any[] }> = {};
  await Promise.all(strategyList.value.map(async s => {
    try {
      const res = await fetch(`/api/backtest/${s.key}`);
      const d = await res.json();
      results[s.key] = { equity: d.equity_curve || [], bench: d.bench_curve || [] };
    } catch {}
  }));
  allCurves.value = results;
  // 等 DOM 更新后渲染所有图表
  setTimeout(() => initAllCharts(), 50);
}

function initAllCharts() {
  for (const s of strategyList.value) {
    const el = chartRefs[s.key];
    if (!el) continue;
    const curve = allCurves.value[s.key];
    if (!curve?.equity?.length) continue;

    // dispose old if exists
    if (charts[s.key]) charts[s.key].dispose();

    const chart = echarts.init(el, "dark");
    charts[s.key] = chart;

    const dates = curve.equity.map((d: any) => d.date);
    const values = curve.equity.map((d: any) => d.value);

    const series: any[] = [
      {
        name: s.label,
        type: "line",
        data: values,
        lineStyle: { color: s.color, width: 1.5 },
        itemStyle: { color: s.color },
        symbol: "none",
        smooth: true,
      },
    ];

    // 基准线
    if (curve.bench?.length) {
      series.push({
        name: "上证指数",
        type: "line",
        data: curve.bench.map((d: any) => d.value),
        lineStyle: { color: "rgba(255,255,255,0.12)", width: 1, type: "dashed" },
        itemStyle: { color: "rgba(255,255,255,0.12)" },
        symbol: "none",
      });
    }

    chart.setOption({
      tooltip: { trigger: "axis" },
      legend: {
        data: [s.label, "上证指数"],
        textStyle: { color: "#62666d", fontSize: 10 },
        top: 0, right: 0, orient: "horizontal",
      },
      grid: { left: 50, right: 15, top: 25, bottom: 20 },
      xAxis: {
        type: "category", data: dates,
        axisLabel: { show: false },
        axisLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
      },
      yAxis: {
        type: "value",
        axisLabel: { formatter: "{value}", fontSize: 10, color: "#62666d" },
        splitLine: { lineStyle: { color: "rgba(255,255,255,0.05)" } },
      },
      series,
    });
  }
}

onMounted(async () => {
  const regRes = await fetch("/api/strategies");
  const regData = await regRes.json();
  if (regData.registry?.length) {
    strategyList.value = regData.registry.map((r: any) => ({ key: r.name, label: r.label, color: r.color }));
  }
  const ovRes = await fetch("/api/backtest");
  overview.value = await ovRes.json();
  if (!strategyList.value.length) {
    strategyList.value = Object.keys(overview.value.strategies || {}).map(k => ({ key: k, label: k, color: "#06b6d4" }));
  }
  await loadAllDetails();
});

onUnmounted(() => {
  Object.values(charts).forEach(c => c.dispose());
});
</script>
