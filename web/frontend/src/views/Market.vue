<template>
  <div class="market-command">
    <section class="market-hero" :class="{ 'is-refreshing': refreshing }">
      <div class="regime-panel glass-card">
        <div class="panel-head">
          <span>MARKET REGIME</span>
        </div>
        <div class="regime-core">
          <div class="regime-orb" :style="{ '--orb-color': regimeColor, '--orb-score': `${displayScore}%` }">
            <div class="regime-orb-inner"></div>
          </div>
          <div>
            <div class="regime-name" :style="{ color: regimeColor }">{{ regimeLabel }}</div>
          </div>
        </div>
        <div class="regime-metrics">
          <div><span>Regime Score</span><strong>{{ displayScoreText }}</strong></div>
          <div><span>A-share Breadth</span><strong>{{ fmtRatioPct(displayBreadth) }}</strong></div>
          <div><span>Volume Trend</span><strong>{{ store.regime?.volume_trend || '—' }}</strong></div>
          <div><span>Max Positions</span><strong>{{ displayPoolSize || '—' }}</strong></div>
          <div><span>Index Trend</span><strong>{{ fmtRatioPct(regimeTrendStrength) }}</strong></div>
          <div><span>Above MA20</span><strong>{{ fmtRatioPct(aboveMa20Ratio) }}</strong></div>
        </div>
      </div>

      <div class="index-panel glass-card">
        <div class="panel-head">
          <span>CORE INDEX RELATIVE STRENGTH</span>
          <div class="time-tabs">
            <span v-for="t in timeRanges" :key="t.key" :class="{ active: selectedRange === t.key }" @click="switchRange(t.key)">{{ t.label }}</span>
          </div>
        </div>
        <div class="index-summary">
          <strong>{{ strengthLeader.label }}</strong>
          <span :style="{ color: displayStrengthPct >= 0 ? 'var(--positive)' : 'var(--negative)' }">
            {{ fmtSignedPct(displayStrengthPct) }}
          </span>
          <em>{{ relativeSubtitle }}</em>
        </div>
        <div class="index-chart-shell">
          <div v-if="relativeChart.lines.length" class="index-legend">
            <span v-for="line in relativeChart.lines" :key="line.key">
              <i :style="{ background: line.color }"></i>{{ line.label }}
            </span>
          </div>
          <div v-if="relativeChart.lines.length" class="chart-y-labels" aria-hidden="true">
            <span
              v-for="tick in chartTicks"
              :key="tick"
              :style="{ top: chartLabelTop(tick) }"
            >{{ fmtSignedPct(tick) }}</span>
          </div>
          <svg
            v-if="relativeChart.lines.length"
            class="index-chart"
            :viewBox="`0 0 ${CHART_VIEW_W} ${CHART_VIEW_H}`"
            preserveAspectRatio="none"
            role="img"
            aria-label="核心指数相对强弱走势图"
          >
            <g class="chart-grid">
              <line
                v-for="tick in chartTicks"
                :key="`grid-${tick}`"
                :x1="CHART_LEFT"
                :x2="CHART_RIGHT"
                :y1="chartY(tick)"
                :y2="chartY(tick)"
              />
            </g>
            <g class="chart-lines" :class="{ 'is-drawing': refreshing }">
              <path
                v-for="line in relativeChart.lines"
                :key="line.key"
                :d="linePath(line)"
                :stroke="line.color"
                :stroke-width="line.key === strengthLeader.key ? 2.8 : 1.9"
                pathLength="1000"
              />
            </g>
          </svg>
          <div v-if="relativeChart.lines.length" class="chart-x-labels" aria-hidden="true">
            <span
              v-for="label in chartXLabels"
              :key="label.date"
              :style="{ left: label.left }"
            >{{ label.label }}</span>
          </div>
          <div v-if="!relativeChart.lines.length" class="panel-empty chart-empty">暂无核心指数对比数据</div>
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
            <strong :style="{ color: macroColor(m) }">{{ fmtValue(macroRef(m.key).value, m.unit) }}</strong>
            <em>prev {{ fmtValue(m.prev, m.unit) }}</em>
            <svg :viewBox="`0 0 ${SPARK_W} ${SPARK_H}`" preserveAspectRatio="none" class="microline">
              <defs>
                <clipPath :id="sparkClipId(m.key)" clipPathUnits="userSpaceOnUse">
                  <rect x="0" y="0" :width="SPARK_W * sparkReveal" :height="SPARK_H" />
                </clipPath>
              </defs>
              <path
                :d="sparkPath(m.series, SPARK_W, SPARK_H)"
                :stroke="macroColor(m)"
                :clip-path="`url(#${sparkClipId(m.key)})`"
              />
            </svg>
          </article>
        </div>
        <div v-if="!macro.length" class="panel-empty">暂无宏观指标数据</div>
      </div>
    </section>

    <div v-if="store.error" class="inline-alert danger">
      <span>{{ store.error }}</span>
      <button class="btn btn-xs" @click="refresh">重试</button>
    </div>

    <section class="sector-pulse glass-card" :class="{ 'is-refreshing': refreshing }">
      <div class="panel-head">
        <span>HOT SECTOR PULSE</span>
        <small>{{ sectorPulseMeta }}</small>
      </div>
      <div v-if="hotSectors.length" class="sector-pulse-grid">
        <article v-for="sector in hotSectors" :key="sector.sector_code" class="sector-pulse-card">
          <div class="sector-rank">#{{ sector.rank }}</div>
          <div class="sector-main">
            <strong>{{ sector.sector_name }}</strong>
            <span>{{ sectorTag(sector) }}</span>
          </div>
          <div class="sector-metrics">
            <div><span>1D</span><strong :style="{ color: colorPct(sector.return_1d) }">{{ fmtReturn(sector.return_1d) }}</strong></div>
            <div><span>5D</span><strong :style="{ color: colorPct(sector.return_5d) }">{{ fmtReturn(sector.return_5d) }}</strong></div>
            <div><span>20D</span><strong :style="{ color: colorPct(sector.return_20d) }">{{ fmtReturn(sector.return_20d) }}</strong></div>
            <div><span>Signal</span><strong>{{ fmtSignalPower(sector) }}</strong></div>
          </div>
        </article>
      </div>
      <div v-else class="panel-empty sector-empty">
        {{ sectorLoading ? "正在加载行业热点..." : "暂无行业热点数据" }}
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useMarketStore } from "../stores";
import { api, type MacroCard, type MarketAssetCard, type MarketSeriesPoint, type SectorCard, type SectorOverviewResponse } from "../api";

const store = useMarketStore();
const selectedRange = ref("6M");
const sectorOverview = ref<SectorOverviewResponse | null>(null);
const sectorLoading = ref(false);

const CHART_VIEW_W = 720;
const CHART_VIEW_H = 310;
const CHART_LEFT = 44;
const CHART_RIGHT = 702;
const CHART_TOP = 34;
const CHART_BOTTOM = 282;
const CHART_WIDTH = CHART_RIGHT - CHART_LEFT;
const CHART_HEIGHT = CHART_BOTTOM - CHART_TOP;
const SPARK_W = 120;
const SPARK_H = 34;
const SPARK_PAD_X = 2;

const timeRanges = [
  { key: "1D", label: "1D" },
  { key: "1M", label: "1M" },
  { key: "6M", label: "6M" },
  { key: "YTD", label: "YTD" },
];

const assets = computed(() => store.multiAsset || []);
const macro = computed(() => store.macro || []);
const hotSectors = computed(() => {
  const sectors = sectorOverview.value?.sectors || [];
  return [...sectors].sort((a, b) => a.rank - b.rank).slice(0, 5);
});
const sectorPulseMeta = computed(() => {
  const total = sectorOverview.value?.total_sectors || 0;
  const date = sectorDate.value;
  if (!total) return "Top 5 · 等待行业快照";
  return `Top 5 / ${total} · ${date}`;
});
const sectorDate = computed(() => {
  const raw = sectorOverview.value?.freshness?.performance || "";
  const m = raw.match(/(\d{4}-\d{2}-\d{2})|(\d{8})/);
  if (!m) return "—";
  const value = m[1] || m[2];
  return value.length === 8 ? `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}` : value;
});

const indexColors: Record<string, string> = {
  sse: "#7dd3fc",
  csi300: "#22c55e",
  chinext: "#f59e0b",
  star50: "#a78bfa",
};

interface RelativeLine {
  key: string;
  label: string;
  color: string;
  change: number;
  data: Array<number | null>;
}

const relativeChart = computed(() => {
  const cards = (assets.value || []).filter((asset: MarketAssetCard) => (asset.series || []).length >= 2);
  const dates = Array.from(new Set(cards.flatMap((asset: MarketAssetCard) => (asset.series || []).map(p => p.date)))).sort();
  const lines: RelativeLine[] = cards.map((asset: MarketAssetCard) => {
    const points = (asset.series || [])
      .map(p => ({ date: p.date, value: Number(p.value) }))
      .filter(p => p.date && Number.isFinite(p.value))
      .sort((a, b) => a.date.localeCompare(b.date));
    const base = points.find(p => p.value !== 0)?.value || 0;
    const values = new Map(points.map(p => [p.date, p.value]));
    const data = dates.map(date => {
      const value = values.get(date);
      if (!base || value == null || !Number.isFinite(value)) return null;
      return Number((((value / base) - 1) * 100).toFixed(2));
    });
    const finite = data.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
    return {
      key: asset.key,
      label: asset.label,
      color: indexColors[asset.key] || "#7dd3fc",
      change: finite.length ? finite[finite.length - 1] : 0,
      data,
    };
  }).filter(line => line.data.some(v => v != null));
  return { dates, lines };
});

const strengthLeader = computed(() => {
  const [leader] = [...relativeChart.value.lines].sort((a, b) => b.change - a.change);
  return leader || { key: "", label: "—", color: "var(--text-disabled)", change: 0, data: [] };
});
const relativeSubtitle = computed(() => {
  const dates = relativeChart.value.dates;
  const rangeText = dates.length ? `${dates[0]} → ${dates[dates.length - 1]}` : "等待指数序列";
  return `${rangeText} · fresh ${store.freshness?.market || "—"}`;
});

const regimeLabel = computed(() => {
  const r = store.regime?.value;
  if (r === "bull") return "EXPANSION";
  if (r === "bear") return "CONTRACTION";
  return "SIDEWAYS";
});
const regimeColor = computed(() => {
  const r = store.regime?.value;
  if (r === "bull") return "var(--positive)";
  if (r === "bear") return "var(--negative)";
  return "var(--warning)";
});
const regimeScore = computed(() => {
  const s = store.regime?.score;
  const n = Number(s);
  if (Number.isFinite(n)) return Number(n.toFixed(1));
  return 50;
});
const displayScoreText = computed(() => displayScore.value.toFixed(1));
const regimeTrendStrength = computed(() => store.regime?.score_components?.trend_raw ?? null);
const aboveMa20Ratio = computed(() => store.regime?.breadth_detail?.above_ma20 ?? null);

const chartScale = computed(() => {
  const values = relativeChart.value.lines
    .flatMap(line => line.data)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
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
  return Array.from({ length: 5 }, (_, i) => Number((max - step * i).toFixed(2)));
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
function shortDate(date: string) {
  const m = date.match(/^\d{4}-(\d{2})-(\d{2})/);
  return m ? `${m[1]}-${m[2]}` : date;
}

async function switchRange(range: string) {
  selectedRange.value = range;
  await store.fetchMarket(range);
}

function fmtValue(v: number | null | undefined, unit = "") {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v);
  const digits = unit === "%" ? 2 : Math.abs(n) >= 100 ? 2 : 3;
  return `${n.toFixed(digits)}${unit}`;
}
function fmtSignedPct(v: number | null | undefined) {
  const n = Number(v || 0);
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}
function fmtRatioPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return "—";
  const n = Number(v) * 100;
  return `${n.toFixed(0)}%`;
}
function fmtReturn(v: number) {
  const n = Number(v || 0) * 100;
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}
function colorPct(v: number) {
  if (v > 0.005) return "var(--positive)";
  if (v < -0.005) return "var(--negative)";
  return "var(--text-secondary)";
}
function signalPower(sector: SectorCard) {
  const ratios = Object.values(sector.signals || {}).map(signal => Number(signal.buy_ratio || 0));
  if (!ratios.length) return 0;
  return Math.max(...ratios);
}
function fmtSignalPower(sector: SectorCard) {
  return `${Math.round(signalPower(sector) * 100)}%`;
}
function sectorTag(sector: SectorCard) {
  const sig = signalPower(sector);
  if (sector.return_20d > 0.10 && sector.volatility > 0.24) return "OVERHEATED";
  if (sig >= 0.5 && sector.return_5d > 0) return "SIGNAL-BACKED";
  if (sector.return_5d > 0 && sector.return_20d > 0) return "MOMENTUM";
  return "WATCH";
}
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
  const drawableWidth = Math.max(width - SPARK_PAD_X * 2, 1);
  return vals.map((v, i) => {
    const x = vals.length === 1 ? width / 2 : SPARK_PAD_X + (i / (vals.length - 1)) * drawableWidth;
    const y = height - ((v - min) / spread) * (height - 6) - 3;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function sparkPath(series: MarketSeriesPoint[] = [], width = 160, height = 44) {
  const pts = sparkPoints(series, width, height);
  if (!pts) return "";
  const arr = pts.split(" ");
  return `M ${arr[0]} L ${arr.slice(1).join(" ")}`;
}

const refreshing = ref(false);
const displayScore = ref(50);
const sparkReveal = ref(1);

let scoreTimer = 0;
let sparkFrame = 0;

// Generic number tween — used for score + all data metrics
function tweenTo(ref: { value: number }, target: number, decimals = 0, duration = 600) {
  const start = ref.value;
  if (start === target) return;
  const startTime = performance.now();
  function tick(now: number) {
    const t = Math.min((now - startTime) / duration, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    const val = start + (target - start) * eased;
    ref.value = decimals > 0 ? Number(val.toFixed(decimals)) : Math.round(val);
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function animateScore(target: number) {
  clearTimeout(scoreTimer);
  tweenTo(displayScore, target, 1, 700);
}

// Animated display values for key metrics
const displayBreadth = ref(0);
const displayPoolSize = ref(0);
const displayStrengthPct = ref(0);
const macroDisplay: Record<string, { ref: ReturnType<typeof ref<number>> }> = {};

function macroRef(key: string) {
  if (!macroDisplay[key]) macroDisplay[key] = { ref: ref(0) };
  return macroDisplay[key].ref;
}

function animateMetrics() {
  tweenTo(displayBreadth, store.regime?.breadth ?? 0, 2, 500);
  tweenTo(displayPoolSize, store.poolSize ?? 0, 0, 500);
  tweenTo(displayStrengthPct, strengthLeader.value.change, 2, 500);
  for (const m of macro.value) {
    const v = Number(m.value);
    if (!isNaN(v)) tweenTo(macroRef(m.key), v, 2, 500);
  }
}

function animateSparklines() {
  cancelAnimationFrame(sparkFrame);
  sparkReveal.value = 0;
  const duration = 600;
  const startTime = performance.now();

  function tick(now: number) {
    const t = Math.min((now - startTime) / duration, 1);
    sparkReveal.value = 1 - Math.pow(1 - t, 3);
    if (t < 1) {
      sparkFrame = requestAnimationFrame(tick);
    } else {
      sparkFrame = 0;
    }
  }

  sparkFrame = requestAnimationFrame(tick);
}

function sparkClipId(key: string) {
  return `macro-spark-${String(key).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

async function refresh() {
  refreshing.value = true;
  sparkReveal.value = 0;
  animateScore(0);
  scoreTimer = window.setTimeout(() => {
    scoreTimer = 0;
  }, 200);

  try {
    await Promise.all([
      store.fetchMarket(selectedRange.value),
      fetchHotSectors(),
    ]);
  } finally {
    setTimeout(() => {
      refreshing.value = false;
      animateScore(regimeScore.value);
      animateMetrics();
      animateSparklines();
    }, 400);
  }
}

async function fetchHotSectors() {
  sectorLoading.value = true;
  try {
    sectorOverview.value = await api.sectorOverview();
  } catch {
    sectorOverview.value = null;
  } finally {
    sectorLoading.value = false;
  }
}

onMounted(() => {
  refresh();
});

onUnmounted(() => {
  clearTimeout(scoreTimer);
  cancelAnimationFrame(sparkFrame);
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
  display: flex;
  align-items: center;
  justify-content: center;
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
.icon-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.regime-panel, .index-panel, .macro-panel {
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
  animation: orb-breathe 3.2s ease-in-out infinite;
}
@keyframes orb-breathe {
  0%, 100% { transform: scale(1); opacity: 0.9; box-shadow: 0 0 8px var(--orb-color); }
  50%      { transform: scale(1.08); opacity: 1; box-shadow: 0 0 14px var(--orb-color), 0 0 26px var(--orb-color); }
}
.regime-name {
  font-size: 22px;
  line-height: 1;
  font-weight: 750;
  letter-spacing: 0.03em;
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
.regime-metrics span, .macro-grid span {
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
.index-summary {
  height: 46px;
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.index-summary strong {
  color: var(--text-primary);
  font-size: 22px;
}
.index-summary span {
  font-family: "JetBrains Mono", monospace;
  font-size: 13px;
  font-weight: 700;
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
.index-chart {
  width: 100%;
  height: 310px;
  display: block;
}
.index-legend {
  position: absolute;
  z-index: 2;
  top: 2px;
  right: 8px;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px 12px;
  max-width: calc(100% - 72px);
}
.index-legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-disabled);
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  white-space: nowrap;
}
.index-legend i {
  width: 10px;
  height: 3px;
  border-radius: 999px;
}
.chart-grid line {
  stroke: rgba(125, 211, 252, 0.06);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}
.chart-lines path {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
  vector-effect: non-scaling-stroke;
  stroke-dasharray: 1000;
  stroke-dashoffset: 0;
  transition: stroke-dashoffset 0.8s ease-out;
}
.chart-lines.is-drawing path {
  transition: stroke-dashoffset 0s;
  stroke-dashoffset: 1000;
}
.chart-y-labels,
.chart-x-labels {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.chart-y-labels span,
.chart-x-labels span {
  position: absolute;
  color: var(--text-disabled);
  font-family: "JetBrains Mono", monospace;
  font-size: 9px;
  line-height: 1;
}
.chart-y-labels span {
  left: 0;
  transform: translateY(-50%);
}
.chart-x-labels span {
  bottom: 3px;
  transform: translateX(-50%);
}
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
.microline {
  width: 100%;
  margin-top: 10px;
}
.microline path {
  fill: none;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}
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
.sector-pulse {
  padding: 10px 14px;
}
.sector-pulse-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-top: 8px;
}
.sector-pulse-card {
  min-height: 86px;
  padding: 8px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.12);
}
.sector-rank {
  color: var(--accent);
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
}
.sector-main {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-top: 4px;
}
.sector-main strong {
  min-width: 0;
  color: var(--text-primary);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sector-main span {
  flex-shrink: 0;
  color: var(--text-disabled);
  font-family: "JetBrains Mono", monospace;
  font-size: 8px;
  letter-spacing: 0.06em;
}
.sector-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 4px;
  margin-top: 8px;
}
.sector-metrics div {
  min-width: 0;
  padding: 4px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(3, 10, 18, 0.22);
}
.sector-metrics span {
  display: block;
  color: var(--text-disabled);
  font-size: 8px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.sector-metrics strong {
  display: block;
  margin-top: 2px;
  color: var(--text-secondary);
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  white-space: nowrap;
}
.sector-empty {
  margin-top: 12px;
  min-height: 110px;
}
@media (max-width: 1180px) {
  .market-hero {
    grid-template-columns: 1fr;
  }
  .sector-pulse-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .market-command { padding: 12px; }
  .macro-grid { grid-template-columns: 1fr; }
  .sector-pulse-grid { grid-template-columns: 1fr; }
  .sector-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .regime-core { grid-template-columns: 1fr; justify-items: center; text-align: center; }
}

/* Refresh shimmer — brief pulse across all data panels */
.market-hero.is-refreshing .glass-card,
.sector-pulse.is-refreshing {
  position: relative;
  overflow: hidden;
}
.market-hero.is-refreshing .glass-card::after,
.sector-pulse.is-refreshing::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(105deg, transparent 40%, rgba(0, 212, 255, 0.06) 50%, transparent 60%);
  animation: shimmer-sweep 0.8s ease-out;
  pointer-events: none;
  z-index: 1;
}
@keyframes shimmer-sweep {
  0%   { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}
</style>
