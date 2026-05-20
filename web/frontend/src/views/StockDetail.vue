<template>
  <div class="view-page stock-detail-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">个股详情</h1>
        <p class="page-subtitle">{{ stock ? `${stock.basic.name} · ${stock.basic.symbol}` : '等待股票数据载入' }}</p>
      </div>
    </div>

    <div v-if="stock" class="space-y-5 animate-fade-in">
      <!-- Basic -->
      <div class="glass-card card-pad-lg">
        <div class="flex items-center gap-3 mb-4">
          <div class="text-2xl font-bold font-mono" style="color:var(--accent)">{{ stock.basic.symbol }}</div>
          <div class="text-xl font-semibold" style="color:var(--text-primary)">{{ stock.basic.name }}</div>
        </div>
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
          <div><span style="color:var(--text-disabled)">行业</span><div class="mt-0.5" style="color:var(--text-secondary)">{{ stock.basic.industry || '—' }}</div></div>
          <div><span style="color:var(--text-disabled)">地区</span><div class="mt-0.5" style="color:var(--text-secondary)">{{ stock.basic.area || '—' }}</div></div>
          <div><span style="color:var(--text-disabled)">市场</span><div class="mt-0.5" style="color:var(--text-secondary)">{{ stock.basic.market || '—' }}</div></div>
        </div>
      </div>

      <!-- Buffett + DCF -->
      <div v-if="stock.buffett" class="glass-card glow-cyan card-pad-lg">
        <div class="section-heading mb-4">巴菲特量化分析</div>
        <div class="detail-metric-grid">
          <div class="detail-metric">
            <div class="detail-metric-label">巴菲特综合评分</div>
            <div class="text-2xl font-bold font-mono" :style="{ color: scoreColor }">{{ stock.buffett.score?.toFixed(0) || '—' }}</div>
          </div>
          <div class="detail-metric">
            <div class="detail-metric-label">净资产收益率</div>
            <div class="text-lg font-mono mt-1" style="color:var(--text-secondary)">{{ fmtPctValue(stock.buffett.roe) }}</div>
          </div>
          <div class="detail-metric">
            <div class="detail-metric-label">销售毛利率</div>
            <div class="text-lg font-mono mt-1" style="color:var(--text-secondary)">{{ fmtPctValue(stock.buffett.gross_margin) }}</div>
          </div>
          <div class="detail-metric">
            <div class="detail-metric-label">产权比率</div>
            <div class="text-lg font-mono mt-1" style="color:var(--text-secondary)">{{ fmtNumber(stock.buffett.debt_equity, 2) }}</div>
          </div>
        </div>
        <div v-if="stock.buffett.dcf_value" class="dcf-line">
          <span class="text-[10px]" style="color:var(--text-disabled)">DCF 内在价值: </span>
          <span class="text-sm font-mono" style="color:var(--accent)">¥{{ fmtNumber(stock.buffett.dcf_value, 2) }}</span>
        </div>
      </div>

      <!-- K-line -->
      <div v-if="stock.kline?.length" class="glass-card card-pad-lg">
        <div class="section-heading mb-4">K 线图</div>
        <div ref="chartRef" style="height:340px"></div>
      </div>

      <!-- Signals -->
      <div v-if="stock.signals" class="glass-card card-pad-lg">
        <div class="section-heading mb-4">策略信号</div>
        <div class="table-shell" style="--table-min:420px">
          <table class="data-table">
            <colgroup>
              <col style="width:40%">
              <col style="width:30%">
              <col style="width:30%">
            </colgroup>
            <thead>
              <tr><th>策略</th><th class="text-right">评分</th><th class="text-right">信号</th></tr>
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
    <div v-else-if="loaded" class="glass-card card-pad-lg empty-panel">
      未找到该股票或当前数据源暂无详情
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed, nextTick } from "vue";
import { useRoute } from "vue-router";
import { api } from "../api";
import { useECharts, QUANTUM_THEME } from "../charts/useECharts";
import type { StockDetail } from "../api";

const route = useRoute();
const stock = ref<StockDetail | null>(null);
const loaded = ref(false);
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
  loaded.value = false;
  try {
    stock.value = await api.stock(code);
    await nextTick();
    if (stock.value?.kline?.length) renderKline();
  } catch {
    stock.value = null;
  } finally {
    loaded.value = true;
  }
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

function fmtPctValue(v: number | undefined | null) {
  return v == null || Number.isNaN(Number(v)) ? "—" : `${(Number(v) * 100).toFixed(1)}%`;
}

function fmtNumber(v: number | undefined | null, digits = 2) {
  return v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(digits);
}

onMounted(load);
watch(() => route.params.code, load);
</script>

<style scoped>
.stock-detail-page {
  gap: 14px;
}
.detail-metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
.detail-metric {
  padding: 14px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: rgba(3, 10, 18, 0.28);
  text-align: center;
}
.detail-metric-label {
  margin-bottom: 4px;
  color: var(--text-disabled);
  font-size: 10px;
}
.dcf-line {
  margin-top: 14px;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: rgba(3, 10, 18, 0.28);
}
.empty-panel {
  min-height: 140px;
  display: grid;
  place-items: center;
  color: var(--text-disabled);
  font-size: 12px;
}
@media (max-width: 900px) {
  .detail-metric-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 520px) {
  .detail-metric-grid {
    grid-template-columns: 1fr;
  }
}
</style>
