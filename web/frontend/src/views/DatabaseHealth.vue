<template>
  <div class="db-health view-page">
    <!-- Hero summary -->
    <section class="health-hero">
      <article class="telemetry-card glass-card">
        <div class="metric-head"><span>{{ t('database.logicalTables') }}</span></div>
        <div class="metric-main">
          <strong style="color:var(--accent)">{{ summary?.tables ?? '—' }}</strong>
          <span>{{ t('database.tablesUnit') }}</span>
        </div>
      </article>

      <article class="telemetry-card glass-card">
        <div class="metric-head"><span>{{ t('database.dataVolume') }}</span></div>
        <div class="metric-main">
          <strong style="color:var(--positive)">{{ fmtSize(summary?.total_size_mb) }}</strong>
          <span>{{ t('database.total') }}</span>
        </div>
      </article>

      <article class="telemetry-card glass-card">
        <div class="metric-head"><span>{{ t('database.missingValues') }}</span></div>
        <div class="metric-main">
          <strong :style="{ color: missingColor }">{{ fmtPercent(summary?.avg_missing_pct) }}</strong>
          <span>{{ t('database.average') }}</span>
        </div>
      </article>

      <article class="telemetry-card glass-card">
        <div class="metric-head"><span>{{ t('database.outliers') }}</span></div>
        <div class="metric-main">
          <strong :style="{ color: outlierColor }">{{ fmtCount(summary?.total_outliers) }}</strong>
          <span>{{ t('database.outliersTotal') }}</span>
        </div>
      </article>
    </section>

    <!-- Status bar -->
    <div class="status-bar">
      <span class="status-dot" :class="statusClass"></span>
      <span v-if="statusText">{{ statusText }}</span>
      <span class="env-tag" :class="apiFallback ? 'env-on' : 'env-off'">
        API_FALLBACK: {{ apiFallback ? 'ON' : 'OFF' }}
      </span>
      <span v-if="summary?.checked_at" class="checked-at">
        {{ t('database.lastChecked', { time: fmtTime(summary.checked_at) }) }}
      </span>
    </div>

    <!-- Table -->
    <div class="table-wrap glass-card">
      <table>
        <colgroup>
          <col style="width:180px">
          <col style="width:128px">
          <col style="width:86px">
          <col style="width:64px">
          <col style="width:72px">
          <col style="width:88px">
          <col style="width:92px">
          <col style="width:92px">
          <col style="width:92px">
          <col style="width:92px">
          <col style="width:92px">
          <col style="width:72px">
          <col style="width:72px">
        </colgroup>
        <thead>
          <tr>
            <th>{{ t('database.tableName') }}</th>
            <th>{{ t('database.dataSource') }}</th>
            <th class="num">{{ t('database.rows') }}</th>
            <th class="num">{{ t('database.columns') }}</th>
            <th class="num">{{ t('database.files') }}</th>
            <th class="num">{{ t('database.size') }}</th>
            <th class="num">{{ t('database.missing10y') }}</th>
            <th class="num" style="opacity:0.5">{{ t('database.missing10yPlus') }}</th>
            <th class="num">{{ t('database.outlier10y') }}</th>
            <th class="num" style="opacity:0.5">{{ t('database.outlier10yPlus') }}</th>
            <th class="num">{{ t('database.freshness') }}</th>
            <th>{{ t('database.detail') }}</th>
            <th>{{ t('database.repair') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(row, i) in sortedRows" :key="row.table">
            <tr :class="{ 'row-error': row.error }">
              <td class="table-name" :title="row.table">
                <span class="name-text">{{ row.label_zh || row.table }}</span>
                <span v-if="row.error" class="error-badge" :title="row.error">!</span>
              </td>
              <td class="source-cell">{{ row.source || '—' }}</td>
              <td class="num">{{ fmtCount(row.rows) }}</td>
              <td class="num">{{ row.columns }}</td>
              <td class="num">{{ row.files || 1 }}</td>
              <td class="num mono">{{ fmtSize(row.size_mb) }}</td>
              <td class="num">
                <span :class="missingClass(row.missing_pct_10y)">{{ fmtMiss10y(row) }}</span>
              </td>
              <td class="num" style="opacity:0.5">
                <span class="val-dim">{{ fmtMiss10yPlus(row) }}</span>
              </td>
              <td class="num">
                <span :class="outlierClass(row.outlier_count_10y)">{{ fmtCountOk(row.outlier_count_10y) }}</span>
              </td>
              <td class="num" style="opacity:0.5">
                <span :class="okClass(row.outlier_count_10y_plus)">{{ fmtCountOk(row.outlier_count_10y_plus) }}</span>
              </td>
              <td class="num">
                <span :class="freshnessClass(row.freshness_days)">
                  {{ freshnessLabel(row.freshness_days) }}
                </span>
              </td>
              <td class="detail-cell">
                <button
                  v-if="hasDetail(row)"
                  class="detail-btn"
                  @click="toggleDetail(row.table)"
                >{{ expanded === row.table ? t('common.collapse') : t('common.expand') }}</button>
              </td>
              <td class="repair-cell">
                <button
                  v-if="row.repairable"
                  class="repair-btn"
                  :disabled="repairing[row.table] === 'running'"
                  @click="startRepair(row.table)"
                >
                  <span v-if="repairing[row.table] === 'running'" class="spinning">...</span>
                  <span v-else-if="repairing[row.table] === 'done'">OK</span>
                  <span v-else-if="repairing[row.table] === 'failed'">ERR</span>
                  <span v-else>{{ t('database.repair') }}</span>
                </button>
                <span v-else class="repair-na">—</span>
              </td>
            </tr>

            <!-- Expanded detail row -->
            <tr v-if="expanded === row.table" class="detail-row">
              <td :colspan="13">
                <div class="detail-panel">
                  <div v-if="row.missing_cols && Object.keys(row.missing_cols).length" class="detail-section">
                    <strong>{{ t('database.missingByColumn') }}</strong>
                    <div class="tag-list">
                      <span v-for="(pct, col) in row.missing_cols" :key="col" class="health-tag tag-warn">
                        {{ col }}: {{ pct }}%
                      </span>
                    </div>
                  </div>
                  <div v-if="row.outlier_cols && Object.keys(row.outlier_cols).length" class="detail-section">
                    <strong>{{ t('database.outlierByColumn') }}</strong>
                    <div class="tag-list">
                      <span v-for="(cnt, col) in row.outlier_cols" :key="col" class="health-tag tag-outlier">
                        {{ col }}: {{ cnt }}
                      </span>
                    </div>
                  </div>
                  <div v-if="row.error" class="detail-section">
                    <strong>{{ t('database.error') }}</strong>
                    <p class="error-text">{{ row.error }}</p>
                  </div>
                  <div v-if="row.time_breakdown && Object.keys(row.time_breakdown).length" class="detail-section">
                    <strong>{{ t('database.timeBreakdown') }}</strong>
                    <div class="breakdown-grid">
                      <div v-for="(info, period) in row.time_breakdown" :key="period" class="breakdown-row">
                        <span class="bd-period">{{ period }}</span>
                        <span class="bd-rows">{{ t('database.rowUnit', { count: info.rows }) }}</span>
                        <span class="bd-missing" :class="bdMissingClass(info.missing_pct)">{{ t('database.missingShort', { value: info.missing_pct }) }}</span>
                        <span class="bd-outlier" v-if="info.outliers && Object.keys(info.outliers).length">{{ t('database.outlierShort', { count: Object.values(info.outliers).reduce((a,b)=>a+b,0) }) }}</span>
                        <span v-if="info.missing_cols && Object.keys(info.missing_cols).length" class="bd-cols">
                          <span v-for="(pct, col) in info.missing_cols" :key="col" class="health-tag tag-warn">{{ col }}:{{ pct }}%</span>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useDatabaseHealth } from "../view-models/useDatabaseHealth";

const { rows, currentLocale, t, summary, status, statusMessage, expanded, apiFallback, repairing, sortedRows, statusClass, statusText, missingColor, outlierColor, fmtSize, fmtPercent, fmtCountOk, fmtCount, fmtTime, fmtMiss10y, fmtMiss10yPlus, freshnessLabel, missingClass, okClass, missingClassAny, outlierClass, outlierClassAny, freshnessClass, bdMissingClass, hasDetail, toggleDetail, startRepair, fetchData } = useDatabaseHealth();
</script>

<style scoped src="../styles/views/database-health.css"></style>
