<template>
  <div class="p-6 space-y-6">
    <h1 class="text-lg font-semibold text-white/90">个股深挖</h1>
    <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
      <div class="flex gap-3">
        <input v-model="query" @keyup.enter="search" placeholder="输入股票代码 (如 600519)" class="flex-1 bg-white/5 border border-white/10 rounded px-3 py-2 text-sm font-mono" />
        <button @click="search" class="px-6 py-2 text-sm rounded bg-[#7170ff] hover:bg-[#8b8aff]">查询</button>
      </div>
    </div>

    <div v-if="stock" class="space-y-4">
      <div class="grid grid-cols-2 gap-4">
        <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
          <h2 class="text-sm font-medium text-white/60 mb-3">基本信息</h2>
          <dl class="space-y-2 text-xs"><div class="flex justify-between"><dt class="text-white/40">代码</dt><dd class="font-mono text-white/70">{{ stock.basic.symbol }}</dd></div><div class="flex justify-between"><dt class="text-white/40">名称</dt><dd class="text-white/70">{{ stock.basic.name }}</dd></div><div class="flex justify-between"><dt class="text-white/40">行业</dt><dd class="text-white/70">{{ stock.basic.industry }}</dd></div></dl>
        </div>
        <div v-if="stock.buffett_result" class="bg-[#111214] border border-white/5 rounded-lg p-4">
          <h2 class="text-sm font-medium text-white/60 mb-3">巴菲特评分</h2>
          <dl class="space-y-2 text-xs"><div class="flex justify-between"><dt class="text-white/40">评分</dt><dd class="text-white/70">{{ stock.buffett_result.score }}</dd></div><div class="flex justify-between"><dt class="text-white/40">ROE(5y)</dt><dd class="text-white/70">{{ stock.buffett_result.avg_roe_5y?.toFixed(1) }}%</dd></div><div class="flex justify-between"><dt class="text-white/40">安全边际</dt><dd class="text-white/70">{{ stock.buffett_result.safety_margin_pct?.toFixed(1) }}%</dd></div></dl>
        </div>
      </div>
      <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
        <h2 class="text-sm font-medium text-white/60 mb-3">K线</h2>
        <div ref="chartRef" style="height:300px"></div>
      </div>
    </div>
    <div v-else class="text-center text-white/30 py-12">输入股票代码查询</div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from "vue";
import * as echarts from "echarts";
import { useRouter } from "vue-router";

const router = useRouter();
const query = ref("");
const stock = ref<any>(null);
const chartRef = ref<HTMLDivElement>();
let chart: echarts.ECharts | null = null;

async function search() {
  if (!query.value) return;
  try {
    const res = await fetch(`/api/stocks/${query.value}`);
    if (res.ok) {
      stock.value = await res.json();
      initChart();
    }
  } catch {}
}

function initChart() {
  if (!chartRef.value || !stock.value?.kline?.length) return;
  if (!chart) chart = echarts.init(chartRef.value, "dark");
  const dates = stock.value.kline.map((k: any) => k.date);
  chart.setOption({
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: dates, axisLabel: { show: false } },
    yAxis: { type: "value", scale: true },
    series: [{
      type: "candlestick",
      data: stock.value.kline.map((k: any) => [k.open, k.close, k.low, k.high]),
      itemStyle: { color: "#ef4444", color0: "#22c55e" },
    }],
  });
}

onUnmounted(() => chart?.dispose());
</script>
