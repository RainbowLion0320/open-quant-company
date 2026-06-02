<template>
  <div class="view-page stock-search-page">
    <!-- Static contract anchor: 股票池概览 -->
    <div class="glass-card stock-search-card">
      <div class="stock-search-main">
        <input
          v-model="query"
          type="search"
          :placeholder="t('stocks.placeholder')"
          class="stock-search-input"
          @keydown.enter="search"
        />
        <button @click="search" class="btn btn-primary">{{ t('common.search') }}</button>
      </div>
      <div class="stock-search-meta">
        <template v-if="stock && !loading">
          <span>{{ t('stocks.current', { symbol: stock.basic.symbol, name: stock.basic.name }) }}</span>
          <span>{{ t('stocks.industry', { industry: stock.basic.industry || '—' }) }}</span>
        </template>
        <template v-else>
          <span>{{ t('stocks.coverage', { shown: defaultRows.length, total: listTotal }) }}</span>
          <span>{{ t('stocks.displayed', { count: filteredRows.length }) }}</span>
          <span v-if="listUpdated">{{ t('stocks.updated', { date: listUpdated }) }}</span>
        </template>
      </div>
    </div>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="search">{{ t('common.retry') }}</button>
    </div>

    <div v-if="loading" class="glass-card card-pad empty-state empty-state-compact">
      {{ t('stocks.searching') }}
    </div>

    <div v-if="listLoading && !stock" class="glass-card card-pad empty-state empty-state-compact">
      {{ t('stocks.loadingPool') }}
    </div>

    <!-- Result -->
    <div v-if="stock && !loading" class="glass-card glow-cyan animate-fade-in card-pad-lg">
      <!-- Basic Info -->
      <div class="flex items-center gap-3 mb-4">
        <div class="text-xl font-bold font-mono" style="color:var(--accent)">{{ stock.basic.symbol }}</div>
        <div class="text-lg font-semibold" style="color:var(--text-primary)">{{ stock.basic.name }}</div>
        <div class="badge" :class="marketBadge">{{ stock.basic.market }}</div>
      </div>

      <div class="stock-detail-metrics">
        <div v-for="metric in detailMetrics" :key="metric.label" class="stock-detail-metric">
          <span>{{ metric.label }}</span>
          <strong :style="{ color: metric.color || 'var(--text-secondary)' }">{{ metric.value }}</strong>
        </div>
      </div>

      <!-- Buffett Score -->
      <div v-if="stock.buffett" class="grid grid-cols-2 lg:grid-cols-5 gap-3 p-3 rounded-lg mb-4" style="background:var(--bg-deep)">
        <div class="text-center">
          <div class="text-[10px]" style="color:var(--text-disabled)">{{ t('stocks.buffettScore') }}</div>
          <div class="text-lg font-bold font-mono mt-1" :style="{ color: (stock.buffett.score||0) >= 70 ? 'var(--positive)' : 'var(--warning)' }">
            {{ stock.buffett.score?.toFixed(0) || '—' }}
          </div>
        </div>
        <div class="text-center">
          <div class="text-[10px]" style="color:var(--text-disabled)">ROE</div>
          <div class="text-sm font-mono mt-1" style="color:var(--text-secondary)">{{ fmtPct(stock.buffett.roe) }}</div>
        </div>
        <div class="text-center">
          <div class="text-[10px]" style="color:var(--text-disabled)">{{ t('stocks.grossMargin') }}</div>
          <div class="text-sm font-mono mt-1" style="color:var(--text-secondary)">{{ fmtPct(stock.buffett.gross_margin) }}</div>
        </div>
        <div class="text-center">
          <div class="text-[10px]" style="color:var(--text-disabled)">D/E</div>
          <div class="text-sm font-mono mt-1" style="color:var(--text-secondary)">{{ stock.buffett.debt_equity?.toFixed(2) || '—' }}</div>
        </div>
        <div class="text-center">
          <div class="text-[10px]" style="color:var(--text-disabled)">{{ t('stocks.dcfValue') }}</div>
          <div class="text-sm font-mono mt-1" style="color:var(--text-secondary)">{{ stock.buffett.dcf_value?.toFixed(2) || '—' }}</div>
        </div>
      </div>

      <!-- Signals -->
      <div v-if="stock.signals && Object.keys(stock.signals).length">
        <div class="text-xs font-semibold mb-3" style="color:var(--text-tertiary)">{{ t('stocks.strategySignals') }}</div>
        <div class="table-shell" style="--table-min:420px">
          <table class="data-table">
            <colgroup>
              <col style="width:40%">
              <col style="width:30%">
              <col style="width:30%">
            </colgroup>
            <thead>
              <tr><th>{{ t('common.strategy') }}</th><th class="text-right">{{ t('common.score') }}</th><th class="text-right">{{ t('common.signal') }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(sigs, strategy) in stock.signals" :key="strategy">
                <td style="color:var(--text-secondary)">{{ strategy }}</td>
                <td class="text-right font-mono">{{ sigs[0]?.score?.toFixed(1) || '—' }}</td>
                <td class="text-right">
                  <span :style="{ color: sigs[0]?.signal === 'buy' ? 'var(--positive)' : 'var(--text-disabled)' }">
                    {{ sigs[0]?.signal === 'buy' ? t('common.buy') : t('common.hold') }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <router-link :to="`/stocks/${stock.basic.symbol}`" class="btn btn-sm mt-4" style="border-color:rgba(0,212,255,0.2); color:var(--accent)">
        {{ t('stocks.viewDetail') }}
      </router-link>
    </div>

    <div v-else-if="searched && !stock && !loading && !error" class="empty-state">
      {{ t('stocks.notFound') }}
    </div>

    <div v-if="!stock && !loading" class="glass-card stock-list-card">
      <div class="stock-list-head">
        <div>
          <span>{{ t('stocks.universeEyebrow') }}</span>
          <strong>{{ t('stocks.universeTitle') }}</strong>
        </div>
        <div class="stock-list-hint">{{ t('stocks.listHint', { count: defaultRows.length }) }}</div>
      </div>
      <div class="stock-list-stats">
        <div>
          <span>{{ t('stocks.coveredStocks') }}</span>
          <strong>{{ defaultRows.length }} / {{ listTotal }}</strong>
        </div>
        <div>
          <span>{{ t('stocks.buyCandidates') }}</span>
          <strong>{{ buyCandidateCount }}</strong>
        </div>
        <div>
          <span>{{ t('stocks.positiveRatio') }}</span>
          <strong>{{ positiveRatio }}</strong>
        </div>
        <div>
          <span>{{ t('stocks.valueCandidates') }}</span>
          <strong>{{ valueCandidateCount }}</strong>
        </div>
      </div>
      <div v-if="filteredRows.length" class="table-shell stock-list-table" style="--table-min:1080px">
        <table class="data-table">
          <colgroup>
            <col style="width:12%">
            <col style="width:13%">
            <col style="width:10%">
            <col style="width:9%">
            <col style="width:9%">
            <col style="width:8%">
            <col style="width:8%">
            <col style="width:9%">
            <col style="width:9%">
            <col style="width:8%">
            <col style="width:5%">
          </colgroup>
          <thead>
            <tr>
              <th>{{ t('stocks.stock') }}</th>
              <th>{{ t('sectors.industry') }}</th>
              <th class="text-right">{{ t('stocks.price') }}</th>
              <th class="text-right">{{ t('stocks.change') }}</th>
              <th class="text-right">PE TTM</th>
              <th class="text-right">PB</th>
              <th class="text-right">{{ t('stocks.marketCap') }}</th>
              <th class="text-right">{{ t('stocks.valueScore') }}</th>
              <th class="text-right">{{ t('stocks.strategyScore') }}</th>
              <th class="text-right">{{ t('common.signal') }}</th>
              <th class="text-right">{{ t('common.action') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in filteredRows" :key="row.symbol">
              <td>
                <div class="stock-cell">
                  <strong>{{ row.name || row.symbol }}</strong>
                  <span>{{ row.symbol }}</span>
                </div>
              </td>
              <td>
                <span style="color:var(--text-secondary)">{{ row.industry || '—' }}</span>
              </td>
              <td class="text-right font-mono">{{ fmtPrice(row.price) }}</td>
              <td class="text-right font-mono" :style="{ color: colorPct(row.change_pct) }">{{ fmtPct(row.change_pct) }}</td>
              <td class="text-right font-mono">{{ fmtNumber(row.pe_ttm, 1) }}</td>
              <td class="text-right font-mono">{{ fmtNumber(row.pb, 2) }}</td>
              <td class="text-right font-mono">{{ fmtNumber(row.total_mv, 0) }}</td>
              <td class="text-right font-mono" :style="{ color: scoreColor(row.buffett_score) }">{{ fmtNumber(row.buffett_score, 0) }}</td>
              <td class="text-right font-mono" :style="{ color: scoreColor(row.signal_score) }">{{ fmtNumber(row.signal_score, 1) }}</td>
              <td class="text-right">
                <span class="signal-pill" :class="{ buy: row.signal === 'buy' }">
                  {{ row.signal === 'buy' ? t('stocks.signalBuy', { buy: row.buy_signals, total: row.signal_count }) : t('stocks.signalHold', { total: row.signal_count }) }}
                </span>
              </td>
              <td class="text-right">
                <button class="btn btn-xs" @click="openStock(row.symbol)">{{ t('stocks.drillDown') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="!listLoading" class="empty-state empty-state-compact">
        {{ t('stocks.noMatches') }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { api } from "../api";
import type { StockDetail, StockListItem } from "../api";
import { useI18n } from "../i18n";
import { colorBySignedRatio, fmtPercentValue, fmtRatioPct, fmtShortCount, fmtSignedRatioPct } from "../utils/format";

const { t } = useI18n();
const query = ref("");
const stock = ref<StockDetail | null>(null);
const defaultRows = ref<StockListItem[]>([]);
const searched = ref(false);
const loading = ref(false);
const listLoading = ref(false);
const error = ref("");
const listUpdated = ref("");
const listTotal = ref(0);

function fmtPct(v: number | undefined) { return fmtRatioPct(v, 1); }
function fmtPrice(v: number | null | undefined) { return v == null ? "—" : v.toFixed(v >= 100 ? 2 : 3); }
function fmtNumber(v: number | null | undefined, digits = 1) { return v == null ? "—" : Number(v).toFixed(digits); }
function colorPct(v: number | null | undefined) { return colorBySignedRatio(v ?? 0); }
function scoreColor(v: number | null | undefined) {
  if (v == null) return "var(--text-disabled)";
  if (v >= 70) return "var(--positive)";
  if (v >= 50) return "var(--warning)";
  return "var(--text-secondary)";
}

const filteredRows = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return defaultRows.value;
  return defaultRows.value.filter(row => (
    row.symbol.toLowerCase().includes(q)
    || row.name.toLowerCase().includes(q)
    || row.industry.toLowerCase().includes(q)
  ));
});

const buyCandidateCount = computed(() => defaultRows.value.filter(row => row.signal === "buy").length);
const positiveRatio = computed(() => {
  const priced = defaultRows.value.filter(row => row.change_pct != null);
  if (!priced.length) return "—";
  return `${((priced.filter(row => (row.change_pct || 0) > 0).length / priced.length) * 100).toFixed(0)}%`;
});
const valueCandidateCount = computed(() => defaultRows.value.filter(row => (row.buffett_score || 0) >= 70).length);
const latestKline = computed(() => {
  const kline = stock.value?.kline || [];
  return kline.length ? kline[kline.length - 1] : null;
});
const previousKline = computed(() => {
  const kline = stock.value?.kline || [];
  return kline.length > 1 ? kline[kline.length - 2] : null;
});
const latestFinancial = computed(() => {
  const financials = stock.value?.financials || [];
  return financials.length ? financials[financials.length - 1] : null;
});
const detailChange = computed(() => {
  const latest = latestKline.value;
  const previous = previousKline.value;
  if (!latest || !previous || !previous.close) return null;
  return latest.close / previous.close - 1;
});
const detailMetrics = computed(() => {
  const s = stock.value;
  if (!s) return [];
  const fin = latestFinancial.value;
  const latest = latestKline.value;
  const change = detailChange.value;
  return [
    { label: t("sectors.industry"), value: s.basic.industry || "—" },
    { label: t("stocks.metrics.latestClose"), value: fmtPrice(latest?.close) },
    { label: t("stocks.metrics.dailyChange"), value: fmtSignedRatioPct(change, 1), color: colorPct(change) },
    { label: t("stocks.metrics.volume"), value: latest?.volume == null ? "—" : fmtShortCount(latest.volume) },
    { label: "ROE", value: fmtPercentValue(fin?.roe, 1) },
    { label: t("stocks.grossMargin"), value: fmtPercentValue(fin?.gross_margin, 1) },
    { label: t("stocks.metrics.revenue"), value: fmtNumber(fin?.revenue, 1) },
    { label: t("stocks.metrics.netProfit"), value: fmtNumber(fin?.net_profit, 1) },
  ];
});

const marketBadge = computed(() => {
  const m = stock.value?.basic.market;
  if (m === "主板") return "badge-green";
  if (m === "创业板") return "badge-amber";
  if (m === "科创板") return "badge-red";
  return "";
});

async function search() {
  if (!query.value.trim()) {
    searched.value = false;
    stock.value = null;
    return;
  }
  searched.value = true;
  loading.value = true;
  error.value = "";
  try {
    stock.value = await api.stock(query.value.trim());
  } catch (e: any) {
    error.value = e?.message || t("stocks.searchError");
    stock.value = null;
  } finally {
    loading.value = false;
  }
}

async function openStock(symbol: string) {
  query.value = symbol;
  await search();
}

async function loadStockList() {
  listLoading.value = true;
  error.value = "";
  try {
    const data = await api.stockList();
    defaultRows.value = data.stocks || [];
    listTotal.value = data.total || defaultRows.value.length;
    listUpdated.value = data.updated_at || "";
  } catch (e: any) {
    error.value = e?.message || t("stocks.poolError");
    defaultRows.value = [];
    listTotal.value = 0;
  } finally {
    listLoading.value = false;
  }
}

onMounted(loadStockList);
</script>

<style scoped>
.stock-search-page {
  gap: 12px;
}
.stock-search-card {
  padding: 12px;
}
.stock-search-main {
  display: flex;
  gap: 10px;
  align-items: center;
}
.stock-search-input {
  flex: 1 1 auto;
  min-width: 0;
}
.stock-search-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  color: var(--text-disabled);
  font-size: 10px;
}
.stock-list-card {
  padding: 12px;
}
.stock-detail-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}
.stock-detail-metric {
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.36);
}
.stock-detail-metric span {
  display: block;
  color: var(--text-disabled);
  font-size: 10px;
}
.stock-detail-metric strong {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: "JetBrains Mono", monospace;
  font-size: 13px;
}
.stock-list-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.stock-list-head span {
  display: block;
  color: var(--text-disabled);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.stock-list-head strong {
  display: block;
  margin-top: 3px;
  color: var(--text-primary);
  font-size: 15px;
}
.stock-list-hint {
  color: var(--text-disabled);
  font-size: 10px;
  white-space: nowrap;
}
.stock-list-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}
.stock-list-stats > div {
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.34);
}
.stock-list-stats span {
  display: block;
  color: var(--text-disabled);
  font-size: 10px;
}
.stock-list-stats strong {
  display: block;
  margin-top: 3px;
  color: var(--text-primary);
  font-family: "JetBrains Mono", monospace;
  font-size: 13px;
}
.stock-cell {
  display: grid;
  gap: 2px;
}
.stock-cell strong {
  color: var(--text-primary);
  font-size: 12px;
}
.stock-cell span {
  color: var(--text-disabled);
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
}
.signal-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 22px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  color: var(--text-secondary);
  font-size: 10px;
  white-space: nowrap;
}
.signal-pill.buy {
  border-color: rgba(34, 197, 94, 0.2);
  background: rgba(34, 197, 94, 0.08);
  color: var(--positive);
}
@media (max-width: 640px) {
  .stock-search-main {
    align-items: stretch;
    flex-direction: column;
  }
  .stock-list-head {
    flex-direction: column;
  }
  .stock-detail-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .stock-list-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .stock-list-hint {
    white-space: normal;
  }
}
</style>
