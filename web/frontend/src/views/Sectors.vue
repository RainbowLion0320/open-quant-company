<template>
  <div class="view-page">
    <!-- Static contract anchors: 强势行业 5日 信号分化度 资金集中度 行业资金方块图 资金热力 动量热力 信号热力 -->
    <div class="surface-toolbar sector-toolbar">
      <div class="surface-copy">
        <span>{{ t('sectors.eyebrow') }}</span>
        <strong>{{ t('sectors.title') }}</strong>
      </div>
      <div v-if="overview" class="surface-actions sector-toolbar-actions">
        <div class="sector-toolbar-metrics" :aria-label="t('sectors.summaryAria')">
          <span class="sector-metric">
            <span>{{ t('sectors.strong5d') }}</span>
            <strong class="metric-positive">{{ top5Return }}%</strong>
          </span>
          <span class="sector-metric">
            <span>{{ t('sectors.weak5d') }}</span>
            <strong class="metric-negative">{{ bottom5Return }}%</strong>
          </span>
          <span class="sector-metric">
            <span>{{ t('sectors.signalDispersion') }}</span>
            <strong>{{ overview.signal_dispersion }}</strong>
          </span>
          <span class="sector-metric">
            <span>{{ t('sectors.capitalConcentration') }}</span>
            <strong>{{ capitalConcentration }}</strong>
          </span>
          <span class="sector-metric">
            <span>{{ t('sectors.dataDate') }}</span>
            <strong>{{ perfDate }}</strong>
          </span>
        </div>
        <span class="sector-meta-chip">
          {{ overview.total_sectors }} {{ t('sectors.industries') }} · {{ dataSourceLabel(overview.data_source) }}
        </span>
      </div>
    </div>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="fetchData">{{ t('common.retry') }}</button>
    </div>

    <section v-if="overview" class="sector-radar-layout">
      <div class="glass-card sector-map-card">
        <div class="sector-map-head">
          <div class="sector-map-heading">
            <span class="sector-map-eyebrow">{{ t('sectors.mapEyebrow') }}</span>
            <div class="sector-map-title-row">
              <strong>{{ t('sectors.mapTitle') }}</strong>
              <!-- Static contract anchor: 行业资金方块图 -->
              <div class="block-map-meta">
                <span>{{ t('sectors.area') }}: {{ blockSizeLabel }}</span>
                <span>{{ t('sectors.color') }}: {{ activeBlockHeatMode?.metric }}</span>
                <span>{{ t('sectors.capitalMetric') }}: {{ capitalSourceLabel }}</span>
              </div>
            </div>
          </div>
          <div class="block-mode-tabs" role="tablist" :aria-label="t('sectors.heatModeAria')">
            <button
              v-for="mode in blockHeatModes"
              :key="mode.key"
              type="button"
              :class="{ active: blockHeatMode === mode.key }"
              @click="blockHeatMode = mode.key"
            >{{ mode.label }}</button>
          </div>
        </div>
        <div v-if="sectorBlockTiles.length" class="sector-block-grid" role="img" :aria-label="t('sectors.blockAria')">
          <button
            v-for="tile in sectorBlockTiles"
            :key="tile.sector.sector_code"
            type="button"
            class="industry-block"
            :class="[
              `span-${tile.span}`,
              { active: activeSector === tile.sector.sector_code, 'is-compact': tile.span === 1 },
            ]"
            :style="industryBlockStyle(tile)"
            :aria-label="industryTooltip(tile)"
            :data-tooltip="industryTooltip(tile)"
            @click="toggleSector(tile.sector)"
          >
            <strong class="industry-amount">{{ formatAmount(tile.size) }}</strong>
            <span class="industry-center-stack">
              <span class="industry-name">{{ tile.sector.sector_name }}</span>
              <span class="industry-metric">{{ tile.metricLabel }}</span>
            </span>
          </button>
        </div>
        <div v-else class="empty-state empty-state-compact">{{ t('sectors.noCapitalData') }}</div>
      </div>
    </section>

    <!-- Sector Ranking Table -->
    <div class="glass-card card-pad-lg">
      <div v-if="loading && !overview" class="empty-state empty-state-compact">
        {{ t('sectors.loadingSnapshot') }}
      </div>
      <div v-if="sortedSectors.length" class="table-shell" style="--table-min:780px">
        <table class="data-table">
          <colgroup>
            <col style="width:8%">
            <col style="width:22%">
            <col style="width:12%">
            <col style="width:12%">
            <col style="width:12%">
            <col style="width:12%">
            <col style="width:11%">
            <col style="width:11%">
          </colgroup>
          <thead>
            <tr>
              <th>{{ t('sectors.rank') }}</th>
              <th>{{ t('sectors.industry') }}</th>
              <th class="text-right">{{ t('sectors.day1') }}</th>
              <th class="text-right">{{ t('sectors.day5') }}</th>
              <th class="text-right">{{ t('sectors.day20') }}</th>
              <th class="text-right">{{ t('sectors.day60') }}</th>
              <th class="text-right">{{ t('sectors.volatility') }}</th>
              <th class="text-right">{{ t('sectors.members') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in sortedSectors"
              :key="s.sector_code"
              @click="toggleSector(s)"
              :class="{ 'row-active': activeSector === s.sector_code }"
              style="cursor:pointer"
            >
              <td class="font-mono" style="color:var(--text-disabled)">{{ s.rank }}</td>
              <td>
                <span style="color:var(--text-primary)">{{ s.sector_name }}</span>
                <span v-if="s.sector_code" class="text-2xs ml-2" style="color:var(--text-disabled)">{{ s.sector_code }}</span>
              </td>
              <td class="text-right font-mono" :style="{ color: colorPct(s.return_1d) }">{{ fmtPct(s.return_1d) }}</td>
              <td class="text-right font-mono" :style="{ color: colorPct(s.return_5d) }">{{ fmtPct(s.return_5d) }}</td>
              <td class="text-right font-mono" :style="{ color: colorPct(s.return_20d), fontWeight: '600' }">{{ fmtPct(s.return_20d) }}</td>
              <td class="text-right font-mono" :style="{ color: colorPct(s.return_60d) }">{{ fmtPct(s.return_60d) }}</td>
              <td class="text-right font-mono" style="color:var(--text-secondary)">{{ fmtPct(s.volatility) }}</td>
              <td class="text-right" style="color:var(--text-secondary)">{{ s.member_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="!loading" class="empty-state">
        <span>{{ t('sectors.noSectorSnapshot') }}</span>
      </div>
    </div>

    <!-- Expanded sector detail -->
    <div v-if="activeDetail" class="glass-card card-pad-lg mt-4 animate-fade-in">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-sm font-semibold" style="color:var(--text-primary)">
          {{ activeDetail.sector_name }}
          <span class="text-2xs ml-3" style="color:var(--text-disabled)">{{ activeDetail.sector_code }}</span>
        </h2>
        <button @click="activeSector = ''" class="btn btn-sm btn-ghost">{{ t('common.collapse') }}</button>
      </div>

      <!-- Signal breakdown -->
      <div v-if="Object.keys(activeDetail.signals).length" class="mb-4">
        <h3 class="text-xs mb-2" style="color:var(--text-secondary)">{{ t('sectors.strategySignalDistribution') }}</h3>
        <div class="signal-grid">
          <div v-for="(sig, strat) in activeDetail.signals" :key="strat" class="signal-cell">
            <div class="text-2xs mb-1" style="color:var(--text-disabled)">{{ strat }}</div>
            <div class="flex items-center gap-3">
              <span class="text-sm font-semibold" :style="{ color: sig.buy_ratio > 0.5 ? 'var(--positive)' : 'var(--text-secondary)' }">
                {{ t('sectors.buyRatio', { pct: (sig.buy_ratio * 100).toFixed(0) }) }}
              </span>
              <span class="text-2xs" style="color:var(--text-disabled)">
                {{ sig.buy_count }}/{{ sig.total }} · {{ t('sectors.avgScore') }} {{ sig.avg_score }}
              </span>
            </div>
            <div class="text-2xs mt-1" style="color:var(--accent)">Top: {{ sig.top_symbol || '—' }}</div>
          </div>
        </div>
      </div>

    </div>

  </div>
</template>

<script setup lang="ts">
import { useSectorsView } from "../view-models/useSectorsView";

const { loading, t, error, overview, activeSector, blockHeatMode, blockHeatModes, sortedSectors, top5Return, bottom5Return, activeBlockHeatMode, capitalSourceLabel, blockSizeLabel, capitalConcentration, sectorBlockTiles, perfDate, activeDetail, fmtPct, colorPct, tileSize, blockMetric, blockMetricLabel, sectorBlockSpan, industryNameFontSize, dataSourceLabel, formatAmount, industryTooltip, heatStyle, industryBlockStyle, toggleSector, fetchData } = useSectorsView();
</script>

<style scoped src="../styles/views/sectors.css"></style>
