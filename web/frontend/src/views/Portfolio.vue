<template>
  <div class="view-page">
    <div class="flex items-center justify-between mb-2">
      <span class="text-2xs" style="color:var(--text-disabled)">{{ summary.total_asset ? '¥' + summary.total_asset.toLocaleString() : '—' }}</span>
      <div class="flex gap-2">
        <button class="btn btn-sm" @click="refresh" :disabled="loading">
          {{ loading ? t('portfolio.refreshing') : t('portfolio.refresh') }}
        </button>
        <button class="btn btn-sm btn-primary" @click="loadAll" :disabled="loading">
          {{ t('portfolio.loadData') }}
        </button>
      </div>
    </div>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="loadAll">{{ t('common.retry') }}</button>
    </div>

    <!-- Balance Cards -->
    <div class="grid grid-cols-2 lg:grid-cols-5 gap-3">
      <div class="glass-card metric-card">
        <div class="metric-label">{{ t('portfolio.totalAsset') }}</div>
        <div class="metric-value primary">
          ¥{{ summary.total_asset?.toLocaleString() || '—' }}
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-label">{{ t('portfolio.cash') }}</div>
        <div class="metric-value">
          ¥{{ summary.cash?.toLocaleString() || '—' }}
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-label">{{ t('portfolio.marketValue') }}</div>
        <div class="metric-value">
          ¥{{ summary.market_value?.toLocaleString() || '—' }}
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-label">{{ t('portfolio.totalReturn') }}</div>
        <div class="metric-value" :style="{ color: summary.total_return_pct >= 0 ? 'var(--positive)' : 'var(--negative)' }">
          {{ fmtReturn(summary.total_return_pct) }}
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-label">{{ t('portfolio.peakEquity') }}</div>
        <div class="metric-value">
          ¥{{ (summary.peak_equity || 0).toLocaleString() }}
        </div>
      </div>
    </div>

    <!-- NAV Equity Curve -->
    <div class="glass-card card-pad-lg">
      <div class="flex justify-between items-center mb-3">
        <div class="text-xs font-semibold tracking-wide" style="color:var(--text-secondary)">
          {{ t('portfolio.equityCurve', { days: navData.length }) }}
        </div>
      </div>
      <div ref="chartRef" style="height:280px"></div>
      <div v-if="!navData.length" class="text-xs text-center py-10" style="color:var(--text-disabled)">
        {{ t('portfolio.noNav') }}
      </div>
    </div>

    <!-- Sector Exposure -->
    <div v-if="sectorExposure.length" class="glass-card card-pad-lg">
      <div class="text-xs font-semibold tracking-wide mb-3" style="color:var(--text-secondary)">
        {{ t('portfolio.sectorExposure', { count: sectorExposure.length }) }}
      </div>
      <div class="exposure-bars">
        <div v-for="e in sectorExposure" :key="e.sector" class="exposure-row">
          <span class="exposure-label">{{ e.sector }}</span>
          <div class="exposure-track">
            <div class="exposure-fill" :style="{ width: Math.max((e.weight * 100), 0.5) + '%' }"></div>
          </div>
          <span class="exposure-val">{{ (e.weight * 100).toFixed(1) }}%</span>
        </div>
      </div>
    </div>

    <!-- Positions -->
    <div class="glass-card card-pad-lg">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">
        {{ t('portfolio.positions', { count: positions.length }) }}
      </div>
      <div v-if="positions.length" class="table-shell" style="--table-min:760px">
        <table class="data-table">
          <colgroup>
            <col style="width:13%">
            <col style="width:16%">
            <col style="width:8%">
            <col style="width:12%">
            <col style="width:12%">
            <col style="width:14%">
            <col style="width:13%">
            <col style="width:12%">
          </colgroup>
          <thead>
            <tr>
              <th>{{ t('portfolio.table.code') }}</th>
              <th>{{ t('portfolio.table.name') }}</th>
              <th class="text-right">{{ t('portfolio.table.volume') }}</th>
              <th class="text-right">{{ t('portfolio.table.cost') }}</th>
              <th class="text-right">{{ t('portfolio.table.price') }}</th>
              <th class="text-right">{{ t('portfolio.table.value') }}</th>
              <th class="text-right">{{ t('portfolio.table.pnl') }}</th>
              <th class="text-right">{{ t('portfolio.table.ratio') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in positions" :key="p.code">
              <td class="font-mono" style="color:var(--accent)">{{ p.code }}</td>
              <td>{{ p.name }}</td>
              <td class="text-right font-mono">{{ p.volume }}</td>
              <td class="text-right font-mono">¥{{ p.avg_cost?.toFixed(2) }}</td>
              <td class="text-right font-mono">¥{{ p.current_price?.toFixed(2) }}</td>
              <td class="text-right font-mono">¥{{ (p.market_value || 0).toLocaleString() }}</td>
              <td class="text-right font-mono" :style="{ color: (p.pnl||0) >= 0 ? 'var(--positive)' : 'var(--negative)' }">
                {{ fmtPnl(p.pnl) }}
              </td>
              <td class="text-right font-mono" :style="{ color: (p.pnl_pct||0) >= 0 ? 'var(--positive)' : 'var(--negative)' }">
                {{ (p.pnl_pct || 0).toFixed(1) }}%
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state empty-state-compact">{{ t('portfolio.noPositions') }}</div>
    </div>

    <!-- Trade History -->
    <div class="glass-card card-pad-lg">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">
        {{ t('portfolio.trades', { count: tradeTotal }) }}
      </div>
      <div v-if="trades.length" class="table-shell" style="--table-min:720px">
        <table class="data-table">
          <colgroup>
            <col style="width:16%">
            <col style="width:14%">
            <col style="width:10%">
            <col style="width:14%">
            <col style="width:10%">
            <col style="width:20%">
            <col style="width:16%">
          </colgroup>
          <thead>
            <tr>
              <th>{{ t('portfolio.table.date') }}</th>
              <th>{{ t('portfolio.table.code') }}</th>
              <th>{{ t('portfolio.side') }}</th>
              <th class="text-right">{{ t('portfolio.table.price') }}</th>
              <th class="text-right">{{ t('portfolio.table.volume') }}</th>
              <th class="text-right">{{ t('portfolio.table.amount') }}</th>
              <th>{{ t('common.strategy') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in trades" :key="t.code + t.date + t.side">
              <td class="font-mono text-[10px]">{{ t.date }}</td>
              <td class="font-mono" style="color:var(--accent)">{{ t.code }}</td>
              <td :style="{ color: t.side === 'buy' ? 'var(--positive)' : 'var(--negative)' }">
                {{ t.side === 'buy' ? translate('common.buy') : translate('common.sell') }}
              </td>
              <td class="text-right font-mono">¥{{ t.price?.toFixed(2) }}</td>
              <td class="text-right font-mono">{{ t.volume }}</td>
              <td class="text-right font-mono">¥{{ (t.amount || 0).toLocaleString() }}</td>
              <td class="text-[10px]" style="color:var(--text-tertiary)">{{ t.strategy }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state empty-state-compact">{{ t('portfolio.noTrades') }}</div>
    </div>

    <!-- Order Form -->
    <div class="glass-card card-pad-lg">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">{{ t('portfolio.manualOrder') }}</div>
      <div class="flex flex-col md:flex-row gap-3 md:items-end">
        <div class="flex-1">
          <div class="text-[10px] mb-1" style="color:var(--text-disabled)">{{ t('portfolio.stockCode') }}</div>
          <input v-model="order.symbol" type="text" placeholder="000001" class="w-full" />
        </div>
        <div class="w-full md:w-20">
          <div class="text-[10px] mb-1" style="color:var(--text-disabled)">{{ t('portfolio.side') }}</div>
          <select v-model="order.side" class="w-full">
            <option value="buy">{{ t('common.buy') }}</option>
            <option value="sell">{{ t('common.sell') }}</option>
          </select>
        </div>
        <div class="w-full md:w-24">
          <div class="text-[10px] mb-1" style="color:var(--text-disabled)">{{ t('portfolio.quantity') }}</div>
          <input v-model.number="order.shares" type="number" min="100" step="100" class="w-full" />
        </div>
        <button @click="submitOrder" class="btn btn-primary">{{ t('common.submit') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { usePortfolioView } from "../view-models/usePortfolioView";

const { positions, currentLocale, t, translate, navData, trades, tradeTotal, sectorExposure, error, summary, loading, order, chartRef, fmtPnl, fmtReturn, loadAll, refresh, submitOrder, renderChart } = usePortfolioView();
</script>

<style scoped src="../styles/views/portfolio.css"></style>
