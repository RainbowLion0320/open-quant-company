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
          <div class="time-tabs"><span class="active">1D</span><span>1M</span><span>6M</span><span>YTD</span></div>
        </div>
        <div class="index-summary">
          <strong>{{ latestClose }}</strong>
          <span :style="{ color: indexChange >= 0 ? 'var(--positive)' : 'var(--negative)' }">
            {{ indexChange >= 0 ? '+' : '' }}{{ indexChange.toFixed(2) }}%
          </span>
          <em>fresh {{ store.freshness?.market || '—' }}</em>
        </div>
        <div ref="chartRef" class="index-chart"></div>
      </div>

      <div class="alerts-panel glass-card">
        <div class="panel-head">
          <span>ALERTS</span>
          <small>{{ alerts.length }} active</small>
        </div>
        <div class="alerts-list">
          <div v-for="item in alerts" :key="item.title + item.time" class="alert-row" :class="`alert-${item.level}`">
            <i></i>
            <div>
              <strong>{{ item.title }}</strong>
              <span>{{ item.detail }}</span>
            </div>
            <em>{{ item.time || '—' }}</em>
          </div>
        </div>
      </div>
    </section>

    <section class="asset-strip">
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
      </article>
    </section>

    <section class="lower-grid">
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
      </div>

      <aside class="right-stack">
        <div class="activity-panel glass-card">
          <div class="panel-head">
            <span>HERMES ACTIVITY</span>
            <small>{{ systemAge }}</small>
          </div>
          <div class="token-row">
            <div><span>Tokens</span><strong>{{ fmtNum(system?.token?.total?.total_tokens || 0) }}</strong></div>
            <div><span>Cost</span><strong>${{ (system?.token?.total?.cost_usd || 0).toFixed(4) }}</strong></div>
            <div><span>Sessions</span><strong>{{ system?.token?.hermes?.sessions || 0 }}</strong></div>
          </div>
          <div class="resource-grid">
            <div v-for="r in resources" :key="r.label" class="resource-gauge">
              <span>{{ r.label }}</span>
              <strong>{{ r.value }}%</strong>
              <div><i :style="{ width: `${Math.min(100, r.value)}%`, background: r.color }"></i></div>
            </div>
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
        </div>
      </aside>
    </section>

    <details class="control-deck glass-card">
      <summary>
        <span>STRATEGY PARAMETER BAY</span>
        <em>保留原始策略调参能力，避免占用首屏决策区</em>
      </summary>
      <div v-if="registry.length" class="param-grid">
        <div v-for="s in registry" :key="s.name" class="param-block">
          <div class="param-title" :style="{ color: s.color }">{{ s.label }}</div>

          <template v-if="s.name === 'buffett'">
            <SliderGroup label="ROE ≥" :val="fmtPct(edit.buffett_roe)" :model="edit.buffett_roe" @u="v=>edit.buffett_roe=v" :min="5" :max="30" color="var(--accent)" />
            <SliderGroup label="毛利率 ≥" :val="fmtPct(edit.buffett_gm)" :model="edit.buffett_gm" @u="v=>edit.buffett_gm=v" :min="5" :max="50" color="var(--accent)" />
            <SliderGroup label="D/E ≤" :val="edit.buffett_de.toFixed(1)" :model="edit.buffett_de" @u="v=>edit.buffett_de=v" :min="0.5" :max="3" :step="0.1" color="var(--accent)" />
          </template>

          <template v-if="s.name === 'multifactor'">
            <SliderGroup label="质量" :val="fmtPct(edit.mf_quality)" :model="edit.mf_quality" @u="v=>edit.mf_quality=v" :min="10" :max="60" :step="5" color="var(--positive)" />
            <SliderGroup label="估值" :val="fmtPct(edit.mf_valuation)" :model="edit.mf_valuation" @u="v=>edit.mf_valuation=v" :min="10" :max="60" :step="5" color="var(--positive)" />
            <SliderGroup label="买入阈值" :val="edit.mf_threshold.toString()" :model="edit.mf_threshold" @u="v=>edit.mf_threshold=v" :min="30" :max="75" :step="5" color="var(--positive)" />
          </template>

          <template v-if="s.name === 'cybernetic'">
            <SliderGroup label="牛市仓位" :val="fmtPct(edit.cy_bull_pos)" :model="edit.cy_bull_pos" @u="v=>edit.cy_bull_pos=v" :min="10" :max="50" :step="5" color="var(--positive)" />
            <SliderGroup label="震荡仓位" :val="fmtPct(edit.cy_side_pos)" :model="edit.cy_side_pos" @u="v=>edit.cy_side_pos=v" :min="5" :max="30" :step="5" color="var(--warning)" />
            <SliderGroup label="熊市仓位" :val="fmtPct(edit.cy_bear_pos)" :model="edit.cy_bear_pos" @u="v=>edit.cy_bear_pos=v" :min="1" :max="15" color="var(--negative)" />
          </template>

          <template v-if="s.name === 'ml_lgbm'">
            <p class="param-note">Regime-aware LightGBM 由周度训练管线更新，参数记录在模型注册表。</p>
          </template>
        </div>
      </div>
      <div class="param-actions">
        <button @click="resetParams" class="btn btn-ghost btn-sm">重置</button>
        <button @click="saveParams" class="btn btn-primary btn-sm">保存参数</button>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, reactive, watch } from "vue";
import { useMarketStore } from "../stores";
import { useECharts, QUANTUM_THEME } from "../charts/useECharts";
import SliderGroup from "../components/SliderGroup.vue";
import { api, type SystemMonitor, type MarketSeriesPoint, type MacroCard } from "../api";

const store = useMarketStore();
const system = ref<SystemMonitor | null>(null);
const chartRef = ref<HTMLElement | null>(null);
const { init: initChart, setOption } = useECharts(chartRef);

const assets = computed(() => store.multiAsset || []);
const macro = computed(() => store.macro || []);
const matrix = computed(() => store.strategyMatrix || []);
const alerts = computed(() => store.alerts || []);
const registry = computed(() => store.registry || []);

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
  const r = store.regime?.value;
  if (r === "bull") return 82;
  if (r === "bear") return 24;
  return 56;
});
const systemAge = computed(() => system.value?.timestamp?.slice?.(11, 19) || "no telemetry");
const resources = computed(() => [
  { label: "CPU", value: Math.round(system.value?.cpu?.percent || 0), color: "var(--accent)" },
  { label: "MEM", value: Math.round(system.value?.memory?.percent || 0), color: "var(--positive)" },
  { label: "DISK", value: Math.round(system.value?.disk?.percent || 0), color: "var(--warning)" },
]);

const edit = reactive({
  buffett_roe: 15, buffett_gm: 30, buffett_de: 1.5,
  dcf_discount: 8, dcf_terminal: 3, dcf_margin: 30,
  mf_quality: 40, mf_valuation: 30, mf_technical: 15, mf_market: 15, mf_threshold: 45,
  cy_bull_pos: 30, cy_bull_stop: -8, cy_side_pos: 15, cy_bear_pos: 5,
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
        sampling: false,
        smooth: false,
        showSymbol: false,
        connectNulls: true,
        lineStyle: { width: 2, color: "#7dd3fc" },
        itemStyle: { color: "#7dd3fc" },
      },
      { type: "bar", data: volumes, sampling: false, xAxisIndex: 1, yAxisIndex: 1, itemStyle: { color: "rgba(0,212,255,0.18)" } },
    ],
  });
}
watch(() => store.kline, renderChart);

function fmtPct(v: number) { return v.toFixed(0) + "%"; }
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
function fmtNum(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
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

function loadFromConfig() {
  const c = store.config; if (!c.buffett) return;
  const b = c.buffett?.moat || {};
  const d = c.buffett?.margin_of_safety || {};
  edit.buffett_roe = (b.min_roe || 0.15) * 100;
  edit.buffett_gm = (b.min_gross_margin || 0.30) * 100;
  edit.buffett_de = b.max_debt_equity || 1.5;
  edit.dcf_discount = (d.dcf_discount_rate || 0.08) * 100;
  edit.dcf_terminal = (d.growth_rate_terminal || 0.03) * 100;
  edit.dcf_margin = (d.safety_margin_pct || 0.30) * 100;
  const m = c.signals?.multifactor || c.multifactor || {}; const w = m.weights || {};
  edit.mf_quality = (w.quality || 0.40) * 100;
  edit.mf_valuation = (w.valuation || 0.30) * 100;
  edit.mf_technical = (w.technical || 0.15) * 100;
  edit.mf_market = (w.market || 0.15) * 100;
  const cy = c.cybernetics?.adaptive || {};
  edit.cy_bull_pos = (cy.bull?.position_size || 0.30) * 100;
  edit.cy_bull_stop = (cy.bull?.stop_loss || -0.08) * 100;
  edit.cy_side_pos = (cy.sideways?.position_size || 0.15) * 100;
  edit.cy_bear_pos = (cy.bear?.position_size || 0.05) * 100;
}

async function saveParams() {
  try {
    const d = await api.settings();
    d.buffett = d.buffett || {}; d.buffett.moat = d.buffett.moat || {};
    d.buffett.moat.min_roe = edit.buffett_roe / 100;
    d.buffett.moat.min_gross_margin = edit.buffett_gm / 100;
    d.buffett.moat.max_debt_equity = edit.buffett_de;
    d.signals = d.signals || {}; d.signals.multifactor = d.signals.multifactor || {};
    d.signals.multifactor.weights = d.signals.multifactor.weights || {};
    d.signals.multifactor.weights.quality = edit.mf_quality / 100;
    d.signals.multifactor.weights.valuation = edit.mf_valuation / 100;
    d.signals.multifactor.weights.technical = edit.mf_technical / 100;
    d.signals.multifactor.weights.market = edit.mf_market / 100;
    d.cybernetics = d.cybernetics || {}; d.cybernetics.adaptive = d.cybernetics.adaptive || {};
    d.cybernetics.adaptive.bull = d.cybernetics.adaptive.bull || {};
    d.cybernetics.adaptive.bull.position_size = edit.cy_bull_pos / 100;
    d.cybernetics.adaptive.bull.stop_loss = edit.cy_bull_stop / 100;
    d.cybernetics.adaptive.sideways = d.cybernetics.adaptive.sideways || {};
    d.cybernetics.adaptive.sideways.position_size = edit.cy_side_pos / 100;
    d.cybernetics.adaptive.bear = d.cybernetics.adaptive.bear || {};
    d.cybernetics.adaptive.bear.position_size = edit.cy_bear_pos / 100;
    await api.saveSettings(d);
    await refresh();
  } catch {}
}
function resetParams() { loadFromConfig(); }
async function refresh() {
  await store.fetchMarket();
  loadFromConfig();
  try { system.value = await api.systemMonitor(); } catch {}
  renderChart();
}

watch(() => store.config, loadFromConfig, { immediate: true });
onMounted(async () => {
  await refresh();
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
  grid-template-columns: 340px minmax(480px, 1fr) 360px;
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
.regime-panel, .index-panel, .alerts-panel, .strategy-panel, .activity-panel, .macro-panel, .control-deck {
  padding: 14px;
}
.regime-core {
  display: grid;
  grid-template-columns: 128px 1fr;
  align-items: center;
  gap: 16px;
  padding: 18px 0;
}
.regime-orb {
  width: 118px;
  height: 118px;
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
  width: 42px;
  height: 42px;
  z-index: 1;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  background: radial-gradient(circle, var(--orb-color), transparent 65%);
}
.regime-name {
  font-size: 25px;
  line-height: 1;
  font-weight: 750;
  letter-spacing: 0.03em;
}
.regime-subtitle {
  margin-top: 8px;
  color: var(--text-tertiary);
  font-size: 12px;
}
.regime-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.regime-metrics div {
  padding: 9px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(0,0,0,0.12);
}
.regime-metrics span, .asset-top span, .resource-gauge span, .macro-grid span {
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
}
.time-tabs .active {
  color: var(--accent);
  border-color: var(--border-default);
  background: rgba(0,212,255,0.06);
}
.index-chart { height: 310px; }
.alerts-list {
  display: flex;
  flex-direction: column;
}
.alert-row {
  display: grid;
  grid-template-columns: 26px 1fr 42px;
  gap: 10px;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.alert-row i {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: 1px solid currentColor;
  opacity: 0.72;
}
.alert-row strong {
  display: block;
  color: var(--text-primary);
  font-size: 12px;
}
.alert-row span, .alert-row em {
  color: var(--text-tertiary);
  font-size: 10px;
  font-style: normal;
}
.alert-success { color: var(--positive); }
.alert-warning { color: var(--warning); }
.alert-danger { color: var(--negative); }
.alert-info { color: var(--accent); }
.asset-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.asset-card {
  padding: 12px 14px;
  min-height: 126px;
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
.lower-grid {
  display: grid;
  grid-template-columns: minmax(620px, 1fr) 420px;
  gap: 12px;
}
.right-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
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
.token-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  padding: 14px 0;
}
.token-row div {
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
}
.token-row span {
  display: block;
  color: var(--text-disabled);
  font-size: 9px;
  text-transform: uppercase;
}
.token-row strong {
  display: block;
  margin-top: 4px;
  color: var(--text-primary);
  font-family: "JetBrains Mono", monospace;
}
.resource-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.resource-gauge {
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
}
.resource-gauge strong {
  display: block;
  margin: 3px 0 8px;
  color: var(--text-primary);
  font-family: "JetBrains Mono", monospace;
}
.resource-gauge div {
  height: 4px;
  border-radius: 4px;
  background: rgba(125,211,252,0.08);
  overflow: hidden;
}
.resource-gauge i {
  display: block;
  height: 100%;
  border-radius: inherit;
}
.macro-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 12px;
}
.macro-grid article {
  min-height: 116px;
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
.control-deck {
  padding: 0;
  overflow: hidden;
}
.control-deck summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 16px;
  cursor: pointer;
  list-style: none;
}
.control-deck summary::-webkit-details-marker { display: none; }
.control-deck summary span {
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.control-deck summary em {
  color: var(--text-disabled);
  font-size: 11px;
  font-style: normal;
}
.param-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 0 16px 16px;
}
.param-block {
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
}
.param-title {
  margin-bottom: 10px;
  font-size: 12px;
  font-weight: 700;
}
.param-note {
  color: var(--text-tertiary);
  font-size: 12px;
}
.param-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px 16px;
}
@media (max-width: 1180px) {
  .market-hero, .lower-grid { grid-template-columns: 1fr; }
  .asset-strip, .param-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .market-command { padding: 12px; }
  .asset-strip, .param-grid, .macro-grid { grid-template-columns: 1fr; }
  .regime-core { grid-template-columns: 1fr; justify-items: center; text-align: center; }
  .command-table { min-width: 720px; }
  .strategy-panel { overflow-x: auto; }
}
</style>
