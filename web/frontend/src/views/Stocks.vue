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
import { useStocksView } from "../view-models/useStocksView";

const { t, query, stock, defaultRows, searched, loading, listLoading, error, listUpdated, listTotal, fmtPct, fmtPrice, fmtNumber, colorPct, scoreColor, filteredRows, buyCandidateCount, positiveRatio, valueCandidateCount, latestKline, previousKline, latestFinancial, detailChange, detailMetrics, marketBadge, search, openStock, loadStockList } = useStocksView();
</script>

<style scoped src="../styles/views/stocks.css"></style>
