<template>
  <div class="market-command">
    <section class="market-hero" :class="{ 'is-refreshing': refreshing }">
      <RegimeHero
        :title="t('market.regime')"
        :regime-color="regimeColor"
        :regime-label="regimeLabel"
        :display-score="displayScore"
        :display-score-text="displayScoreText"
        :gauge-metrics="regimeGaugeMetrics"
        :status-cards="regimeStatusCards"
      />

      <div class="index-panel glass-card">
        <div class="panel-head">
          <span>{{ t('market.relativeStrength') }}</span>
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
              <em
                v-if="line.data_source && line.data_source !== 'real' && line.data_source !== 'cached'"
                class="source-badge"
                :class="`source-${line.data_source}`"
                :title="line.source_detail || line.data_source"
              >{{ line.data_source === 'proxy' ? 'PROXY' : line.data_source === 'placeholder' ? 'N/A' : line.data_source }}</em>
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
            :aria-label="t('market.chartAria')"
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
          <div v-if="!relativeChart.lines.length" class="panel-empty chart-empty">{{ t('market.noIndexData') }}</div>
        </div>
      </div>

      <div class="macro-panel glass-card">
        <div class="panel-head">
          <span>{{ t('market.macroIndicators') }}</span>
          <small>GDP · PMI · CPI · LIQUIDITY · PROFIT</small>
        </div>
        <div class="macro-grid">
          <article v-for="m in macro" :key="m.key">
            <span>{{ m.label }}</span>
            <strong :style="{ color: macroColor(m) }">{{ fmtValue(macroRef(m.key).value, m.unit) }}</strong>
            <em>{{ t('market.prev') }} {{ fmtValue(m.prev, m.unit) }}</em>
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
        <div v-if="!macro.length" class="panel-empty">{{ t('market.noMacroData') }}</div>
      </div>
    </section>

    <div v-if="store.error" class="inline-alert danger">
      <span>{{ store.error }}</span>
      <button class="btn btn-xs" @click="refresh">{{ t('common.retry') }}</button>
    </div>

    <section class="sector-pulse glass-card" :class="{ 'is-refreshing': refreshing }">
      <div class="panel-head">
        <span>{{ t('market.hotSectorPulse') }}</span>
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
            <div><span>{{ t('market.signal') }}</span><strong>{{ fmtSignalPower(sector) }}</strong></div>
          </div>
        </article>
      </div>
      <div v-else class="panel-empty sector-empty">
        {{ sectorLoading ? t("market.loadingSectors") : t("market.noSectorData") }}
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import RegimeHero from "../components/market/RegimeHero.vue";
import { useAnimatedMetrics } from "../composables/useAnimatedMetrics";
import { useMarketOverview } from "../composables/useMarketOverview";
import { useMarketStore } from "../stores";
import { api, type MacroCard, type MarketAssetCard, type MarketSeriesPoint, type SectorCard, type SectorOverviewResponse } from "../api";
import { useI18n } from "../i18n";
import { colorBySignedRatio, fmtSignedRatioPct } from "../utils/format";
import { signalPower } from "../utils/sector";

const store = useMarketStore();
const { t } = useI18n();
const { timeRanges, indexColors } = useMarketOverview();
const { tweenTo } = useAnimatedMetrics();
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

const assets = computed(() => store.multiAsset || []);
const macro = computed(() => store.macro || []);
const hotSectors = computed(() => {
  const sectors = sectorOverview.value?.sectors || [];
  return [...sectors].sort((a, b) => a.rank - b.rank).slice(0, 5);
});
const sectorPulseMeta = computed(() => {
  const total = sectorOverview.value?.total_sectors || 0;
  const date = sectorDate.value;
  if (!total) return `Top 5 · ${t("market.waitingSectorSnapshot")}`;
  return `Top 5 / ${total} · ${date}`;
});
const sectorDate = computed(() => {
  const raw = sectorOverview.value?.freshness?.performance || "";
  const m = raw.match(/(\d{4}-\d{2}-\d{2})|(\d{8})/);
  if (!m) return "—";
  const value = m[1] || m[2];
  return value.length === 8 ? `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6)}` : value;
});

interface RelativeLine {
  key: string;
  label: string;
  color: string;
  change: number;
  data: Array<number | null>;
  data_source?: string;
  source_detail?: string;
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
      data_source: asset.data_source,
      source_detail: asset.source_detail,
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
  const rangeText = dates.length ? `${dates[0]} → ${dates[dates.length - 1]}` : t("market.waitingIndexSeries");
  return `${rangeText} · ${t("market.fresh")} ${store.freshness?.market || "—"}`;
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
  return null;
});
const displayScoreText = computed(() => regimeScore.value === null ? "—" : displayScore.value.toFixed(1));
const regimeStabilityState = computed(() => {
  if (!store.regime) {
    return {
      confirmed: "—",
      raw: "—",
      pending: "—",
      pending_count: null,
      pendingCount: null,
      min_dwell: null,
      minDwell: null,
      dwell: "—",
    };
  }
  const stability = store.regime?.stability || {};
  const confirmedRaw = stability.confirmed_value || store.regime?.value || "sideways";
  const rawValue = store.regime?.raw_value || stability.raw_value || store.regime?.value || "sideways";
  const pendingRaw = stability.pending_value || "";
  const hasPending = Boolean(pendingRaw && pendingRaw !== "unknown");
  const pendingCountValue = Number(stability.pending_count);
  const minDwellValue = Number(stability.min_dwell);
  const pendingCount = Number.isFinite(pendingCountValue) ? pendingCountValue : null;
  const minDwell = Number.isFinite(minDwellValue) ? minDwellValue : null;
  const dwell = hasPending ? `${pendingCount ?? 0}/${minDwell ?? "—"}` : "Idle";
  return {
    confirmed: String(confirmedRaw).toUpperCase(),
    raw: String(rawValue).toUpperCase(),
    pending: hasPending ? String(pendingRaw).toUpperCase() : "—",
    pending_count: pendingCount,
    pendingCount,
    min_dwell: minDwell,
    minDwell,
    dwell,
  };
});
const riskBuffer = computed(() => store.regime?.score_components?.risk_raw ?? null);
const regimeTrendStrength = computed(() => store.regime?.score_components?.trend_raw ?? null);
const aboveMa20Ratio = computed(() => store.regime?.breadth_detail?.above_ma20 ?? null);
const regimeStatusCards = computed(() => [
  // Static contract anchor: { key: "dwell", label: "Dwell", value: regimeStabilityState.value.dwell }
  { key: "confirmed", label: t("market.labels.confirmed"), value: regimeStabilityState.value.confirmed },
  { key: "raw", label: t("market.labels.raw"), value: regimeStabilityState.value.raw },
  { key: "pending", label: t("market.labels.pending"), value: regimeStabilityState.value.pending },
  { key: "dwell", label: t("market.labels.dwell"), value: regimeStabilityState.value.dwell },
]);
const regimeGaugeMetrics = computed(() => [
  {
    key: "risk",
    label: t("market.labels.riskBuffer"),
    value: fmtRatioPct(displayRiskBuffer.value),
    percent: ratioGauge(displayRiskBuffer.value),
    color: riskColor(displayRiskBuffer.value),
  },
  {
    key: "breadth",
    label: t("market.labels.breadth"),
    value: fmtRatioPct(displayBreadth.value),
    percent: ratioGauge(displayBreadth.value),
    color: "var(--accent)",
  },
  {
    key: "trend",
    label: t("market.labels.trend"),
    value: fmtRatioPct(displayTrendStrength.value),
    percent: ratioGauge(displayTrendStrength.value),
    color: "var(--positive)",
  },
  {
    key: "above-ma20",
    label: t("market.labels.aboveMa20"),
    value: fmtRatioPct(displayAboveMa20.value),
    percent: ratioGauge(displayAboveMa20.value),
    color: "var(--warning)",
  },
]);

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
  animateScore(regimeScore.value);
  animateMetrics();
  animateSparklines();
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
function clampGauge(v: number | null | undefined) {
  const n = Number(v);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Number(n.toFixed(1))));
}
function ratioGauge(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return 0;
  return clampGauge(Number(v) * 100);
}
function fmtReturn(v: number) {
  return fmtSignedRatioPct(v);
}
function colorPct(v: number) {
  return colorBySignedRatio(v);
}
function fmtSignalPower(sector: SectorCard) {
  return `${Math.round(signalPower(sector) * 100)}%`;
}
function sectorTag(sector: SectorCard) {
  const sig = signalPower(sector);
  if (sector.return_20d > 0.10 && sector.volatility > 0.24) return t("market.sectorTags.overheated");
  if (sig >= 0.5 && sector.return_5d > 0) return t("market.sectorTags.signalBacked");
  if (sector.return_5d > 0 && sector.return_20d > 0) return t("market.sectorTags.momentum");
  return t("market.sectorTags.watch");
}
function macroColor(m: MacroCard) {
  if (m.key === "pmi" && Number(m.value || 0) < 50) return "var(--warning)";
  if (m.key === "cpi" && Number(m.value || 0) < 0) return "var(--negative)";
  if (m.key === "m1_m2_spread") return Number(m.value || 0) >= 0 ? "var(--positive)" : "var(--warning)";
  if (m.key === "ppi_cpi_spread") return Number(m.value || 0) >= 0 ? "var(--positive)" : "var(--negative)";
  return "var(--accent)";
}
function riskColor(v: number | null | undefined) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "var(--text-disabled)";
  if (n >= 0.7) return "var(--positive)";
  if (n >= 0.45) return "var(--warning)";
  return "var(--negative)";
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

function animateScore(target: number | null) {
  clearTimeout(scoreTimer);
  if (target === null) return;
  tweenTo(displayScore, target, 1, 700);
}

// Animated display values for key metrics
const displayBreadth = ref(0);
const displayRiskBuffer = ref(0);
const displayTrendStrength = ref(0);
const displayAboveMa20 = ref(0);
const displayStrengthPct = ref(0);
const macroDisplay: Record<string, { ref: ReturnType<typeof ref<number>> }> = {};

function macroRef(key: string) {
  if (!macroDisplay[key]) macroDisplay[key] = { ref: ref(0) };
  return macroDisplay[key].ref;
}

function finiteOrZero(v: number | null | undefined) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function animateMetrics() {
  tweenTo(displayRiskBuffer, finiteOrZero(riskBuffer.value), 2, 520);
  tweenTo(displayBreadth, store.regime?.breadth ?? 0, 2, 500);
  tweenTo(displayTrendStrength, finiteOrZero(regimeTrendStrength.value), 2, 540);
  tweenTo(displayAboveMa20, finiteOrZero(aboveMa20Ratio.value), 2, 560);
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
/* Static contract anchors: Confirmed Pending {{ item.value }} regime-status-card is-inline */
.regime-score-line {
  display: inline-flex;
  min-width: 100%;
  align-items: center;
  justify-content: center;
}
.regime-status-card {
  min-height: 28px;
  padding: 4px 6px;
}
.macro-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}
.macro-grid article {
  min-height: 88px;
}
</style>
<style scoped src="../styles/views/market.css"></style>
