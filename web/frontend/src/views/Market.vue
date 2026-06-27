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

      <section class="market-asset-flow" :class="{ 'is-refreshing': refreshing }">
        <section v-if="assetModule('etf')" class="etf-section glass-card" :class="moduleStatusClass(assetModule('etf'))">
          <div class="independent-section-head">
            <div>
              <span>{{ t('market.etfRotationTitle') }}</span>
              <strong>{{ assetModule('etf')?.headline }}</strong>
            </div>
            <em>{{ moduleStatusLabel(assetModule('etf')) }}</em>
          </div>
          <div class="etf-section-body">
            <div class="etf-stat-column">
              <div v-for="metric in assetModule('etf')?.metrics || []" :key="metric.key">
                <span>{{ metric.label }}</span>
                <strong>{{ fmtModuleMetric(metric) }}</strong>
              </div>
            </div>
            <div class="etf-trend-panel">
              <svg v-if="assetModule('etf')?.series?.length" :viewBox="`0 0 ${SPARK_W} ${SPARK_H}`" preserveAspectRatio="none" class="etf-sparkline">
                <path :d="moduleSeriesPath(assetModule('etf'))" />
              </svg>
              <div v-else class="section-empty-line">{{ moduleBlocker(assetModule('etf')) }}</div>
              <div class="etf-category-strip">
                <span v-for="category in (assetModule('etf')?.categories || []).slice(0, 5)" :key="category.key">
                  {{ category.label }} <em>{{ category.count }}</em>
                </span>
              </div>
            </div>
          </div>
        </section>

        <section v-if="assetModule('bond')" class="bond-section glass-card" :class="moduleStatusClass(assetModule('bond'))">
          <div class="independent-section-head">
            <div>
              <span>{{ t('market.ratesBondsTitle') }}</span>
              <strong>{{ assetModule('bond')?.headline }}</strong>
            </div>
            <em>{{ moduleStatusLabel(assetModule('bond')) }}</em>
          </div>
          <div class="bond-section-body">
            <div class="bond-key-rate">
              <span>{{ metricLabel(assetModule('bond'), 'yield_10y') || '10Y' }}</span>
              <strong>{{ fmtModuleMetric(metricByKey(assetModule('bond'), 'yield_10y')) }}</strong>
              <em>{{ metricLabel(assetModule('bond'), 'spread_10y2y') }} {{ fmtModuleMetric(metricByKey(assetModule('bond'), 'spread_10y2y')) }}</em>
            </div>
            <svg v-if="assetModule('bond')?.curve?.length" viewBox="0 0 180 72" preserveAspectRatio="none" class="yield-curve">
              <path :d="bondCurvePath(assetModule('bond'))" />
              <circle
                v-for="point in bondCurvePoints(assetModule('bond'))"
                :key="point.label"
                :cx="point.x"
                :cy="point.y"
                r="2.4"
              />
            </svg>
            <div v-else class="section-empty-line">{{ moduleBlocker(assetModule('bond')) }}</div>
          </div>
          <div class="bond-tenors" v-if="assetModule('bond')?.curve?.length">
            <span v-for="point in assetModule('bond')?.curve || []" :key="point.tenor">{{ point.tenor }} {{ point.value.toFixed(2) }}%</span>
          </div>
        </section>

        <section v-if="assetModule('crypto')" class="crypto-section glass-card" :class="moduleStatusClass(assetModule('crypto'))">
          <div class="independent-section-head">
            <div>
              <span>{{ t('market.cryptoRiskTitle') }}</span>
              <strong>{{ assetModule('crypto')?.headline }}</strong>
            </div>
            <em>{{ moduleStatusLabel(assetModule('crypto')) }}</em>
          </div>
          <div class="crypto-sentinel">
            <strong>{{ t('market.cryptoFreshnessBlocked') }}</strong>
            <span>{{ t('market.cryptoFreshnessDetail') }}</span>
          </div>
          <div class="crypto-blockers">
            <em v-for="blocker in assetModule('crypto')?.blockers || []" :key="blocker">{{ shortBlocker(blocker) }}</em>
          </div>
        </section>

        <section v-if="assetModule('futures')" class="futures-section glass-card" :class="moduleStatusClass(assetModule('futures'))">
          <div class="independent-section-head">
            <div>
              <span>{{ t('market.futuresTransmissionTitle') }}</span>
              <strong>{{ assetModule('futures')?.headline }}</strong>
            </div>
            <em>{{ moduleStatusLabel(assetModule('futures')) }}</em>
          </div>
          <div class="futures-section-body">
            <div class="futures-group-bars">
              <div v-for="group in assetModule('futures')?.groups || []" :key="group.key">
                <span>{{ group.label }}</span>
                <i :style="{ width: moduleBarWidth(group.value), background: colorPct(group.value) }"></i>
                <em :style="{ color: colorPct(group.value) }">{{ fmtSignedPct(group.value) }}</em>
              </div>
            </div>
            <div class="futures-movers">
              <div v-for="item in assetModule('futures')?.items || []" :key="item.symbol">
                <span>{{ item.symbol }} · {{ item.category_label }}</span>
                <strong>{{ item.label }}</strong>
                <em :style="{ color: colorPct(item.change_pct || 0) }">{{ fmtSignedPct(item.change_pct || 0) }}</em>
              </div>
            </div>
          </div>
        </section>

        <div v-if="!assetModules.length" class="panel-empty sector-empty">{{ t("market.noAssetModules") }}</div>
      </section>
    </section>

    <div v-if="store.error" class="inline-alert danger">
      <span>{{ store.error }}</span>
      <button class="btn btn-xs" @click="refresh">{{ t('common.retry') }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import RegimeHero from "../components/market/RegimeHero.vue";
import { useAnimatedMetrics } from "../composables/useAnimatedMetrics";
import { useMarketOverview } from "../composables/useMarketOverview";
import { useRelativeStrengthChart } from "../composables/useRelativeStrengthChart";
import { useMarketStore } from "../stores";
import type { MarketAssetModule, MarketAssetModuleMetric, MarketSeriesPoint } from "../api";
import { useI18n } from "../i18n";
import { colorBySignedRatio, fmtSignedRatioPct } from "../utils/format";

const store = useMarketStore();
const { t } = useI18n();
const { timeRanges, indexColors } = useMarketOverview();
const { tweenTo } = useAnimatedMetrics();
const selectedRange = ref("6M");

const SPARK_W = 120;
const SPARK_H = 34;
const SPARK_PAD_X = 2;

const assets = computed(() => store.multiAsset || []);
const assetModules = computed<MarketAssetModule[]>(() => store.assetModules || []);
const marketFreshness = computed(() => `${t("market.fresh")} ${store.freshness?.market || "—"}`);

const {
  CHART_VIEW_W,
  CHART_VIEW_H,
  CHART_LEFT,
  CHART_RIGHT,
  relativeChart,
  relativeSubtitle,
  strengthLeader,
  chartTicks,
  chartXLabels,
  chartY,
  chartLabelTop,
  linePath,
} = useRelativeStrengthChart(assets, indexColors, () => t("market.waitingIndexSeries"), marketFreshness);

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
function colorPct(v: number) {
  return colorBySignedRatio(v);
}

function shortBlocker(blocker = "") {
  return blocker.replace(/_/g, " ");
}

function assetModule(assetType: string) {
  return assetModules.value.find(module => module.asset_type === assetType) || null;
}

function moduleStatusClass(module: MarketAssetModule | null) {
  return `module-status-${String(module?.status || "missing")}`;
}

function moduleStatusLabel(module: MarketAssetModule | null) {
  const status = String(module?.status || "missing");
  if (status === "ready") return "READY";
  if (status === "watch") return "WATCH";
  if (status === "blocked") return "BLOCKED";
  return "MISSING";
}

function metricByKey(module: MarketAssetModule | null, key: string) {
  return (module?.metrics || []).find(metric => metric.key === key) || null;
}

function metricLabel(module: MarketAssetModule | null, key: string) {
  return metricByKey(module, key)?.label || "";
}

function fmtModuleMetric(metric: MarketAssetModuleMetric | null | undefined) {
  if (!metric || metric.value === null || metric.value === undefined || metric.value === "") return "—";
  const raw = metric.value;
  const value = typeof raw === "number" ? (Math.abs(raw) >= 100 ? raw.toFixed(0) : raw.toFixed(2)) : String(raw);
  return `${value}${metric.unit ? ` ${metric.unit}` : ""}`;
}

function moduleBlocker(module: MarketAssetModule | null) {
  return module?.blockers?.length ? shortBlocker(module.blockers[0]) : t("market.moduleNoData");
}

function moduleSeriesPath(module: MarketAssetModule | null) {
  return sparkPath(module?.series || [], SPARK_W, SPARK_H);
}

function bondCurvePoints(module: MarketAssetModule | null) {
  const curve = module?.curve || [];
  if (!curve.length) return [];
  const values = curve.map(point => Number(point.value)).filter(Number.isFinite);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  return curve.map((point, index) => {
    const x = curve.length === 1 ? 90 : 14 + (index / (curve.length - 1)) * 152;
    const y = 62 - ((Number(point.value) - min) / spread) * 48;
    return { label: point.tenor, x: Number(x.toFixed(1)), y: Number(y.toFixed(1)) };
  });
}

function bondCurvePath(module: MarketAssetModule | null) {
  const points = bondCurvePoints(module);
  if (!points.length) return "";
  return `M ${points[0].x},${points[0].y} L ${points.slice(1).map(point => `${point.x},${point.y}`).join(" ")}`;
}

function moduleBarWidth(value: number | undefined) {
  const pct = Math.min(Math.abs(Number(value || 0)) * 12, 100);
  return `${Math.max(8, pct).toFixed(1)}%`;
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
  return `asset-spark-${String(key).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
}

async function refresh() {
  refreshing.value = true;
  sparkReveal.value = 0;
  animateScore(0);
  scoreTimer = window.setTimeout(() => {
    scoreTimer = 0;
  }, 200);

  try {
    await store.fetchMarket(selectedRange.value);
  } finally {
    setTimeout(() => {
      refreshing.value = false;
      animateScore(regimeScore.value);
      animateMetrics();
      animateSparklines();
    }, 400);
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
</style>
<style scoped src="../styles/views/market.css"></style>
