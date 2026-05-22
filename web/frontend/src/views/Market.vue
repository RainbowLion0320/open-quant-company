<template>
  <div class="market-command">
    <section class="market-hero">
      <div class="regime-panel glass-card">
        <div class="panel-head">
          <span>MARKET REGIME</span>
          <button @click="refresh" class="icon-button" aria-label="刷新">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4" />
            </svg>
          </button>
        </div>
        <div class="regime-core">
          <div class="regime-orb" :style="{ '--orb-color': regimeColor, '--orb-score': `${regimeScore}%` }">
            <div class="regime-orb-inner"></div>
          </div>
          <div>
            <div class="regime-name" :style="{ color: regimeColor }">{{ regimeLabel }}</div>
            <div class="regime-subtitle">{{ regimeDescriptor }}</div>
          </div>
        </div>
        <div class="regime-metrics">
          <div><span>Regime Score</span><strong>{{ regimeScore }}</strong></div>
          <div><span>Market Breadth</span><strong>{{ store.regime?.breadth?.toFixed(2) || '—' }}</strong></div>
          <div><span>Volume Trend</span><strong>{{ store.regime?.volume_trend || '—' }}</strong></div>
          <div><span>Pool Size</span><strong>{{ store.poolSize || '—' }}</strong></div>
        </div>
        <div class="trend-note">{{ store.regime?.ma_trend || '等待市场检测' }}</div>
      </div>

      <div class="index-panel glass-card">
        <div class="panel-head">
          <span>SHANGHAI COMPOSITE INDEX</span>
          <div class="time-tabs">
            <span v-for="t in timeRanges" :key="t.key" :class="{ active: selectedRange === t.key }" @click="switchRange(t.key)">{{ t.label }}</span>
          </div>
        </div>
        <div class="index-summary">
          <strong>{{ latestClose }}</strong>
          <span :style="{ color: indexChange >= 0 ? 'var(--positive)' : 'var(--negative)' }">
            {{ indexChange >= 0 ? '+' : '' }}{{ indexChange.toFixed(2) }}%
          </span>
          <em>fresh {{ store.freshness?.market || '—' }}</em>
        </div>
        <div class="index-chart-shell">
          <div ref="chartRef" class="index-chart"></div>
          <div v-if="!store.kline.length" class="panel-empty chart-empty">暂无指数K线数据</div>
        </div>
      </div>

      <div class="macro-panel glass-card">
        <div class="panel-head">
          <span>MACRO INDICATORS</span>
          <small>GDP · PMI · CPI · SHIBOR</small>
        </div>
        <div class="macro-grid">
          <article v-for="m in macro" :key="m.key">
            <span>{{ m.label }}</span>
            <strong :style="{ color: macroColor(m) }">{{ fmtValue(m.value, m.unit) }}</strong>
            <em>prev {{ fmtValue(m.prev, m.unit) }}</em>
            <svg viewBox="0 0 120 34" preserveAspectRatio="none" class="microline">
              <polyline :points="sparkPoints(m.series, 120, 34)" :stroke="macroColor(m)" />
            </svg>
          </article>
        </div>
        <div v-if="!macro.length" class="panel-empty">暂无宏观指标数据</div>
      </div>
    </section>

    <section v-if="assets.length" class="asset-strip">
      <article v-for="asset in assets" :key="asset.key" class="asset-card glass-card">
        <div class="asset-top">
          <span>{{ asset.label }}</span>
          <em>{{ asset.symbol }}</em>
        </div>
        <div class="asset-value">
          <strong>{{ fmtValue(asset.value, asset.unit) }}</strong>
          <small :style="{ color: (asset.change_pct || 0) >= 0 ? 'var(--positive)' : 'var(--negative)' }">
            {{ fmtPctChange(asset.change_pct) }}
          </small>
        </div>
        <svg viewBox="0 0 160 44" preserveAspectRatio="none" class="sparkline">
          <polyline :points="sparkPoints(asset.series, 160, 44)" :stroke="sparkColor(asset.change_pct)" />
        </svg>
        <div class="asset-source" :title="asset.source_detail || ''">
          <span v-if="asset.data_source === 'real'" class="source-dot source-real"></span>
          <span v-else-if="asset.data_source === 'proxy'" class="source-badge source-proxy">PROXY</span>
          <span v-else-if="asset.data_source === 'missing'" class="source-badge source-missing">NO DATA</span>
          <span v-else class="source-dot source-unknown"></span>
        </div>
      </article>
    </section>
    <section v-else class="asset-strip">
      <article class="asset-card glass-card asset-empty">
        <span>宏观与跨资产数据暂未载入</span>
        <strong>等待数据源刷新</strong>
      </article>
    </section>

    <section class="strategy-section">
      <div class="strategy-panel glass-card">
        <div class="panel-head">
          <span>STRATEGY SIGNAL MATRIX</span>
          <small>{{ matrix.length }} strategies</small>
        </div>
        <table class="command-table">
          <colgroup>
            <col style="width:24%">
            <col style="width:13%">
            <col style="width:12%">
            <col style="width:14%">
            <col style="width:23%">
            <col style="width:14%">
          </colgroup>
          <thead>
            <tr>
              <th>Strategy</th>
              <th>Signal</th>
              <th class="right">Score</th>
              <th class="right">Buy Ratio</th>
              <th>Top Target</th>
              <th>Updated</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in matrix" :key="row.name">
              <td>
                <strong>{{ row.label }}</strong>
                <span>{{ row.name }}</span>
              </td>
              <td><b :class="`signal-${row.signal}`">{{ signalLabel(row.signal) }}</b></td>
              <td class="right font-mono">{{ row.score?.toFixed?.(1) || '0.0' }}</td>
              <td class="right font-mono">{{ (row.buy_ratio * 100).toFixed(1) }}%</td>
              <td>
                <strong>{{ row.top_symbol || '—' }}</strong>
                <span>{{ row.top_name || row.industry || '等待信号' }}</span>
              </td>
              <td class="font-mono">{{ shortTime(row.last_computed) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="!matrix.length" class="panel-empty table-empty">暂无策略矩阵，等待扫描结果</div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useMarketStore } from "../stores";
import { useECharts, QUANTUM_THEME } from "../charts/useECharts";
import type { MacroCard, MarketSeriesPoint } from "../api";

const store = useMarketStore();
const chartRef = ref<HTMLElement | null>(null);
const { init: initChart, setOption } = useECharts(chartRef);
const selectedRange = ref("6M");

const timeRanges = [
  { key: "1D", label: "1D" },
  { key: "1M", label: "1M" },
  { key: "6M", label: "6M" },
  { key: "YTD", label: "YTD" },
];

const assets = computed(() => store.multiAsset || []);
const macro = computed(() => store.macro || []);
const matrix = computed(() => store.strategyMatrix || []);

const latestClose = computed(() => {
  const k = store.kline?.at?.(-1);
  return k ? Number(k.close).toFixed(2) : "—";
});
const indexChange = computed(() => {
  const rows = store.kline || [];
  if (rows.length < 2) return 0;
  const last = rows[rows.length - 1].close;
  const prev = rows[rows.length - 2].close;
  return prev ? ((last / prev - 1) * 100) : 0;
});

const regimeLabel = computed(() => {
  const r = store.regime?.value;
  if (r === "bull") return "EXPANSION";
  if (r === "bear") return "CONTRACTION";
  return "SIDEWAYS";
});
const regimeDescriptor = computed(() => {
  const r = store.regime?.value;
  if (r === "bull") return "Bullish trend / risk-on";
  if (r === "bear") return "Defensive posture / risk-off";
  return "Range-bound / wait for confirmation";
});
const regimeColor = computed(() => {
  const r = store.regime?.value;
  if (r === "bull") return "var(--positive)";
  if (r === "bear") return "var(--negative)";
  return "var(--warning)";
});
const regimeScore = computed(() => {
  const s = store.regime?.score;
  if (s != null) return Math.round(s);
  return 50;
});

function renderChart() {
  if (!store.kline.length) return;
  initChart();
  const dates = store.kline.map((k: any) => k.date);
  const closes = store.kline.map((k: any) => Number(k.close));
  const volumes = store.kline.map((k: any) => k.volume);
  setOption({
    ...QUANTUM_THEME,
    grid: [
      { left: 42, right: 18, top: 12, height: "68%" },
      { left: 42, right: 18, top: "80%", height: "13%" },
    ],
    xAxis: [
      { type: "category", data: dates, gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: "rgba(125,211,252,0.08)" } } },
      { type: "category", data: dates, gridIndex: 1, axisLabel: { color: "#64748b", fontSize: 9 } },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, scale: true, axisLabel: { color: "#64748b", fontSize: 9 }, splitLine: { lineStyle: { color: "rgba(125,211,252,0.05)" } } },
      { type: "value", gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    series: [
      {
        name: "Close",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: closes,
        smooth: false,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { width: 2, color: "#7dd3fc" },
        itemStyle: { color: "#7dd3fc" },
      },
      { type: "bar", data: volumes, xAxisIndex: 1, yAxisIndex: 1, itemStyle: { color: "rgba(0,212,255,0.18)" } },
    ],
  });
}
watch(() => store.kline, renderChart);

async function switchRange(range: string) {
  selectedRange.value = range;
  await store.fetchMarket(range);
  renderChart();
}

function fmtValue(v: number | null | undefined, unit = "") {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const digits = unit === "%" ? 3 : Math.abs(n) >= 100 ? 2 : 3;
  return `${n.toFixed(digits)}${unit}`;
}
function fmtPctChange(v: number | null | undefined) {
  const n = Number(v || 0) * 100;
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}
function shortTime(s: string) { return s ? s.slice(5, 16).replace("T", " ") : "—"; }
function signalLabel(s: string) { return s === "buy" ? "BUY" : s === "sell" ? "SELL" : "HOLD"; }
function sparkColor(v: number | null | undefined) { return Number(v || 0) >= 0 ? "#22c55e" : "#ef4444"; }
function macroColor(m: MacroCard) {
  if (m.key === "pmi" && Number(m.value || 0) < 50) return "var(--warning)";
  if (m.key === "cpi" && Number(m.value || 0) < 0) return "var(--negative)";
  return "var(--accent)";
}
function sparkPoints(series: MarketSeriesPoint[] = [], width = 160, height = 44) {
  if (!series.length) return "";
  const vals = series.map(p => Number(p.value)).filter(Number.isFinite);
  if (!vals.length) return "";
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const spread = max - min || 1;
  return vals.map((v, i) => {
    const x = vals.length === 1 ? width : (i / (vals.length - 1)) * width;
    const y = height - ((v - min) / spread) * (height - 6) - 3;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

async function refresh() {
  await store.fetchMarket(selectedRange.value);
  renderChart();
}

onMounted(async () => {
  await store.fetchMarket(selectedRange.value);
  initChart();
  renderChart();
});
</script>

<style scoped>
.market-command {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.market-hero {
  display: grid;
  grid-template-columns: 280px minmax(480px, 1fr) 340px;
  gap: 12px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}
.panel-head span {
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.panel-head small {
  color: var(--text-disabled);
  font-size: 10px;
}
.icon-button {
  width: 26px;
  height: 26px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(0, 212, 255, 0.04);
  color: var(--accent);
  cursor: pointer;
}
.icon-button svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.regime-panel, .index-panel, .macro-panel, .strategy-panel {
  padding: 14px;
}
.regime-core {
  display: grid;
  grid-template-columns: 110px 1fr;
  align-items: center;
  gap: 14px;
  padding: 14px 0;
}
.regime-orb {
  width: 100px;
  height: 100px;
  position: relative;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: conic-gradient(var(--orb-color) var(--orb-score), rgba(125,211,252,0.08) 0);
  box-shadow: 0 0 32px rgba(0, 212, 255, 0.12);
}
.regime-orb::before {
  content: "";
  position: absolute;
  inset: 10px;
  border-radius: 50%;
  background: var(--bg-panel);
  border: 1px solid var(--border-default);
}
.regime-orb-inner {
  width: 36px;
  height: 36px;
  z-index: 1;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  background: radial-gradient(circle, var(--orb-color), transparent 65%);
}
.regime-name {
  font-size: 22px;
  line-height: 1;
  font-weight: 750;
  letter-spacing: 0.03em;
}
.regime-subtitle {
  margin-top: 6px;
  color: var(--text-tertiary);
  font-size: 11px;
}
.regime-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.regime-metrics div {
  padding: 8px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(0,0,0,0.12);
}
.regime-metrics span, .asset-top span, .macro-grid span {
  display: block;
  color: var(--text-disabled);
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
}
.regime-metrics strong {
  display: block;
  margin-top: 4px;
  color: var(--text-primary);
  font-family: "JetBrains Mono", monospace;
}
.trend-note {
  margin-top: 12px;
  color: var(--text-tertiary);
  font-size: 11px;
}
.index-summary {
  height: 46px;
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.index-summary strong {
  color: var(--positive);
  font-family: "JetBrains Mono", monospace;
  font-size: 26px;
}
.index-summary em {
  margin-left: auto;
  color: var(--text-disabled);
  font-style: normal;
  font-size: 10px;
}
.time-tabs {
  display: flex;
  gap: 4px;
}
.time-tabs span {
  padding: 3px 8px;
  border-radius: 4px;
  color: var(--text-disabled);
  border: 1px solid transparent;
  font-size: 10px;
  cursor: pointer;
  user-select: none;
}
.time-tabs span:hover {
  color: var(--text-secondary);
  border-color: var(--border-subtle);
}
.time-tabs .active {
  color: var(--accent);
  border-color: var(--border-default);
  background: rgba(0,212,255,0.06);
}
.index-chart-shell {
  position: relative;
  min-height: 310px;
}
.index-chart { height: 310px; }
.panel-empty {
  min-height: 120px;
  display: grid;
  place-items: center;
  color: var(--text-disabled);
  font-size: 12px;
  border: 1px dashed rgba(125, 211, 252, 0.08);
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.08);
}
.chart-empty {
  position: absolute;
  inset: 8px 0 0;
  min-height: 0;
}
.table-empty {
  min-height: 86px;
  border-top: 0;
  border-radius: 0 0 7px 7px;
}
.asset-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.asset-card {
  padding: 12px 14px;
  min-height: 126px;
}
.asset-source {
  margin-top: 6px;
  display: flex;
  align-items: center;
}
.source-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  display: inline-block;
}
.source-real { background: #22c55e; box-shadow: 0 0 4px rgba(34,197,94,0.4); }
.source-unknown { background: #64748b; }
.source-badge {
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 1px 5px;
  border-radius: 3px;
  line-height: 1.6;
}
.source-proxy {
  color: #f59e0b;
  background: rgba(245,158,11,0.10);
  border: 1px solid rgba(245,158,11,0.20);
}
.source-missing {
  color: #94a3b8;
  background: rgba(148,163,184,0.10);
  border: 1px solid rgba(148,163,184,0.20);
}
.asset-empty {
  grid-column: 1 / -1;
  display: flex;
  min-height: 92px;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
}
.asset-empty span {
  color: var(--text-disabled);
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.asset-empty strong {
  color: var(--text-secondary);
  font-size: 13px;
}
.asset-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.asset-top em {
  color: var(--text-disabled);
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  font-style: normal;
}
.asset-value {
  margin-top: 12px;
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.asset-value strong {
  color: var(--text-primary);
  font-family: "JetBrains Mono", monospace;
  font-size: 22px;
}
.asset-value small {
  font-family: "JetBrains Mono", monospace;
}
.sparkline, .microline {
  width: 100%;
  margin-top: 10px;
}
.sparkline polyline, .microline polyline {
  fill: none;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}
.strategy-section {
  display: block;
}
.command-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
}
.command-table th {
  height: 34px;
  padding: 10px 10px;
  color: var(--text-disabled);
  border-bottom: 1px solid var(--border-subtle);
  background: rgba(8, 19, 33, 0.34);
  font-size: 10px;
  font-weight: 600;
  text-align: left;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.command-table td {
  height: 42px;
  padding: 11px 10px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}
.command-table tbody tr:last-child td {
  border-bottom: 0;
}
.command-table tbody tr:nth-child(even) td {
  background: rgba(125, 211, 252, 0.014);
}
.command-table td strong {
  display: block;
  color: var(--text-primary);
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.command-table td span {
  display: block;
  color: var(--text-disabled);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.command-table tbody tr:hover td {
  background: rgba(0, 212, 255, 0.055);
}
.right { text-align: right !important; font-variant-numeric: tabular-nums; }
.signal-buy { color: var(--positive); }
.signal-sell { color: var(--negative); }
.signal-hold { color: var(--warning); }
.macro-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
}
.macro-grid article {
  min-height: 108px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(0,0,0,0.12);
}
.macro-grid strong {
  display: block;
  margin-top: 5px;
  font-family: "JetBrains Mono", monospace;
  font-size: 18px;
}
.macro-grid em {
  display: block;
  color: var(--text-disabled);
  font-size: 10px;
  font-style: normal;
}
@media (max-width: 1180px) {
  .market-hero { grid-template-columns: 1fr; }
  .asset-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .market-command { padding: 12px; }
  .asset-strip, .macro-grid { grid-template-columns: 1fr; }
  .regime-core { grid-template-columns: 1fr; justify-items: center; text-align: center; }
  .command-table { min-width: 720px; }
  .strategy-panel { overflow-x: auto; }
}
</style>
