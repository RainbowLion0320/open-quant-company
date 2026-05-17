<template>
  <div class="p-6 space-y-5">
    <div class="page-header">
      <div>
        <h1 class="page-title">个股详情</h1>
        <p class="page-subtitle">{{ stock?.basic.name }} · {{ stock?.basic.symbol }}</p>
      </div>
    </div>

    <div v-if="stock" class="space-y-5 animate-fade-in">
      <!-- Basic -->
      <div class="glass-card" style="padding:20px">
        <div class="flex items-center gap-3 mb-4">
          <div class="text-2xl font-bold font-mono" style="color:var(--accent)">{{ stock.basic.symbol }}</div>
          <div class="text-xl font-semibold" style="color:var(--text-primary)">{{ stock.basic.name }}</div>
        </div>
        <div class="grid grid-cols-4 gap-3 text-xs">
          <div><span style="color:var(--text-disabled)">行业</span><div class="mt-0.5" style="color:var(--text-secondary)">{{ stock.basic.industry }}</div></div>
          <div><span style="color:var(--text-disabled)">地区</span><div class="mt-0.5" style="color:var(--text-secondary)">{{ stock.basic.area }}</div></div>
          <div><span style="color:var(--text-disabled)">市场</span><div class="mt-0.5" style="color:var(--text-secondary)">{{ stock.basic.market }}</div></div>
        </div>
      </div>

      <!-- Buffett + DCF -->
      <div v-if="stock.buffett" class="glass-card glow-cyan" style="padding:20px">
        <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">巴菲特量化分析</div>
        <div class="grid grid-cols-4 gap-4">
          <div class="text-center p-3 rounded-lg" style="background:var(--bg-deep)">
            <div class="text-[10px] mb-1" style="color:var(--text-disabled)">巴菲特综合评分</div>
            <div class="text-2xl font-bold font-mono" :style="{ color: scoreColor }">{{ stock.buffett.score?.toFixed(0) || '—' }}</div>
          </div>
          <div class="text-center p-3 rounded-lg" style="background:var(--bg-deep)">
            <div class="text-[10px] mb-1" style="color:var(--text-disabled)">净资产收益率</div>
            <div class="text-lg font-mono mt-1" style="color:var(--text-secondary)">{{ (stock.buffett.roe * 100).toFixed(1) }}%</div>
          </div>
          <div class="text-center p-3 rounded-lg" style="background:var(--bg-deep)">
            <div class="text-[10px] mb-1" style="color:var(--text-disabled)">销售毛利率</div>
            <div class="text-lg font-mono mt-1" style="color:var(--text-secondary)">{{ (stock.buffett.gross_margin * 100).toFixed(1) }}%</div>
          </div>
          <div class="text-center p-3 rounded-lg" style="background:var(--bg-deep)">
            <div class="text-[10px] mb-1" style="color:var(--text-disabled)">产权比率</div>
            <div class="text-lg font-mono mt-1" style="color:var(--text-secondary)">{{ stock.buffett.debt_equity.toFixed(2) }}</div>
          </div>
        </div>
        <div v-if="stock.buffett.dcf_value" class="mt-4 p-3 rounded-lg" style="background:var(--bg-deep)">
          <span class="text-[10px]" style="color:var(--text-disabled)">DCF 内在价值: </span>
          <span class="text-sm font-mono" style="color:var(--accent)">¥{{ stock.buffett.dcf_value.toFixed(2) }}</span>
        </div>
      </div>

      <!-- K-line -->
      <div v-if="stock.kline?.length" class="glass-card" style="padding:20px">
        <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">K 线图</div>
        <div ref="chartRef" style="height:340px"></div>
      </div>

      <!-- Signals -->
      <div v-if="stock.signals" class="glass-card" style="padding:20px">
        <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">策略信号</div>
        <table class="data-table">
          <thead>
            <tr><th style="width:40%">策略</th><th style="width:30%" class="text-right">评分</th><th style="width:30%" class="text-right">信号</th></tr>
          </thead>
          <tbody>
            <tr v-for="(sigs, strategy) in stock.signals" :key="strategy">
              <td style="color:var(--text-secondary)">{{ strategy }}</td>
              <td class="text-right font-mono">{{ sigs[0]?.score?.toFixed(1) || '—' }}</td>
              <td class="text-right">
                <span :style="{ color: sigs[0]?.signal === 'buy' ? 'var(--positive)' : 'var(--text-disabled)' }">
                  {{ sigs[0]?.signal === 'buy' ? '买入' : '持有' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from "vue";
import { useRoute } from "vue-router";
import { api } from "../api";
import { useECharts, QUANTUM_THEME } from "../charts/useECharts";
import type { StockDetail } from "../api";

const route = useRoute();
const stock = ref<StockDetail | null>(null);
const chartRef = ref<HTMLElement | null>(null);
const { init: initChart, setOption } = useECharts(chartRef);

const scoreColor = computed(() => {
  const s = stock.value?.buffett?.score || 0;
  if (s >= 70) return "var(--positive)";
  if (s >= 50) return "var(--warning)";
  return "var(--negative)";
});

async function load() {
  const code = route.params.code as string;
  if (!code) return;
  try {
    stock.value = await api.stock(code);
    if (stock.value?.kline?.length) renderKline();
  } catch {}
}

function renderKline() {
  if (!stock.value?.kline?.length) return;
  initChart();

  const kline = stock.value.kline;
  const dates = kline.map((k: any) => k.date);
  const ohlc = kline.map((k: any) => [k.open, k.close, k.low, k.high]);
  const volumes = kline.map((k: any) => k.volume);

  setOption({
    ...QUANTUM_THEME,
    grid: [
      { left: 8, right: 8, top: 8, height: "68%" },
      { left: 8, right: 8, top: "80%", height: "14%" },
    ],
    xAxis: [
      { type: "category", data: dates, gridIndex: 0, axisLabel: { show: false } },
      { type: "category", data: dates, gridIndex: 1, axisLabel: { color: "#475569", fontSize: 9 } },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, scale: true, axisLabel: { color: "#64748b", fontSize: 9 }, splitLine: { lineStyle: { color: "rgba(255,255,255,0.03)" } } },
      { type: "value", gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    series: [
      {
        type: "candlestick", data: ohlc,
        itemStyle: { color: "#22c55e", color0: "#ef4444", borderColor: "#22c55e", borderColor0: "#ef4444" },
      },
      {
        type: "bar", data: volumes, xAxisIndex: 1, yAxisIndex: 1,
        itemStyle: { color: "rgba(0,212,255,0.15)" },
      },
    ],
  });
}

onMounted(load);
watch(() => route.params.code, load);
</script>
