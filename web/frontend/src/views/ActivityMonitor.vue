<template>
  <div class="system-page view-page">
    <!-- Static contract anchors: API HEALTH CRON JOBS RESOURCE HISTORY TOP PROCESSES Telegram -->
    <section class="system-hero">
      <article class="telemetry-card glass-card">
        <div class="metric-head">
          <span>CPU</span>
          <small>{{ t('activity.cores', { count: monitor?.cpu?.cores_physical ?? '—' }) }}</small>
        </div>
        <div class="metric-main">
          <strong :style="{ color: cpuColor }">{{ fmtPercent(monitor?.cpu?.percent) }}</strong>
          <span>{{ loadText }}</span>
        </div>
        <div class="meter-track"><i :style="{ width: pctWidth(monitor?.cpu?.percent), background: cpuColor }"></i></div>
        <div class="metric-foot">
          <span>{{ t('activity.loadAverage') }}</span>
          <em>{{ loadText }}</em>
        </div>
      </article>

      <article class="telemetry-card glass-card">
        <div class="metric-head">
          <span>MEMORY</span>
          <small>{{ fmtGb(monitor?.memory?.used_gb) }} / {{ fmtGb(monitor?.memory?.total_gb) }}</small>
        </div>
        <div class="metric-main">
          <strong :style="{ color: memColor }">{{ fmtPercent(monitor?.memory?.percent) }}</strong>
          <span>{{ t('activity.used', { value: fmtGb(monitor?.memory?.used_gb) }) }}</span>
        </div>
        <div class="meter-track"><i :style="{ width: pctWidth(monitor?.memory?.percent), background: memColor }"></i></div>
        <div class="metric-foot">
          <span>{{ t('activity.battery') }}</span>
          <em>{{ batteryText }}</em>
        </div>
      </article>

      <article class="telemetry-card glass-card">
        <div class="metric-head">
          <span>DISK</span>
          <small>{{ fmtGb(monitor?.disk?.used_gb) }} / {{ fmtGb(monitor?.disk?.total_gb) }}</small>
        </div>
        <div class="metric-main">
          <strong style="color:var(--text-secondary)">{{ fmtPercent(monitor?.disk?.percent) }}</strong>
          <span>{{ t('activity.used', { value: fmtGb(monitor?.disk?.used_gb) }) }}</span>
        </div>
        <div class="meter-track"><i :style="{ width: pctWidth(monitor?.disk?.percent), background: 'var(--text-secondary)' }"></i></div>
        <div class="metric-foot">
          <span>{{ t('activity.updatedAgo', { seconds: elapsed }) }}</span>
          <button @click="fetchData" class="icon-button" :aria-label="t('activity.refresh')">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/></svg>
          </button>
        </div>
      </article>
    </section>

    <div v-if="monitorError" class="inline-alert danger">
      <span>{{ monitorError }}</span>
      <button class="btn btn-xs" @click="fetchData">{{ t('common.retry') }}</button>
    </div>

    <section class="system-grid">
      <aside class="system-side">
        <div class="glass-card side-card">
          <div class="panel-head">
            <span>{{ t('activity.resourceHistory') }}</span>
            <small>{{ historyHours }}h</small>
          </div>
          <div class="resource-charts">
            <div>
              <canvas :id="cpuChartId"></canvas>
              <div>CPU %</div>
            </div>
            <div>
              <canvas :id="memChartId"></canvas>
              <div>MEM %</div>
            </div>
          </div>
        </div>

        <div class="glass-card side-card">
          <div class="panel-head">
            <span>{{ t('activity.topProcesses') }}</span>
            <small>{{ t('activity.rows', { count: monitor?.top_processes?.length ?? 0 }) }}</small>
          </div>
          <div class="table-shell compact-table" style="--table-min:0">
            <table class="data-table">
              <colgroup>
                <col style="width:62%"><col style="width:19%"><col style="width:19%">
              </colgroup>
              <thead>
                <tr><th>{{ t('activity.process') }}</th><th class="text-right">CPU</th><th class="text-right">MEM</th></tr>
              </thead>
              <tbody>
                <tr v-for="p in monitor?.top_processes ?? []" :key="p.pid">
                  <td class="font-mono process-name">{{ p.name }}</td>
                  <td class="text-right font-mono">{{ p.cpu }}%</td>
                  <td class="text-right font-mono">{{ p.mem }}%</td>
                </tr>
              </tbody>
            </table>
            <div v-if="!(monitor?.top_processes?.length)" class="mini-empty">{{ t('activity.noProcessSamples') }}</div>
          </div>
        </div>
      </aside>
    </section>

    <section class="ops-grid">
      <div class="glass-card ops-card">
        <div class="panel-head">
          <span>{{ t('activity.apiHealth') }}</span>
          <em v-if="apiHealth" :class="apiHealth.all_ok ? 'source-badge ok' : 'source-badge limited'"
            class="summary-badge">{{ apiHealth.summary }}</em>
        </div>
        <div class="source-list">
          <template v-if="apiHealth && apiHealth.items.length">
            <div v-for="api in apiHealthOrdered" :key="api.name">
              <span>{{ api.name }}</span>
              <em :class="['source-badge', apiBadgeClass(api.status)]">{{ api.detail }}</em>
            </div>
          </template>
          <div v-else><span>{{ t('activity.apiHealth') }}</span><em class="source-badge muted">{{ t('activity.loading') }}</em></div>
        </div>
      </div>
      <div class="glass-card ops-card">
        <div class="panel-head">
          <span>{{ t('activity.cronJobs') }}</span>
          <em v-if="cronSummary" :class="['source-badge', cronSummaryBadge, 'summary-badge']">{{ cronSummary }}</em>
        </div>
        <div class="source-list">
          <template v-if="cronJobs.length">
            <div v-for="job in cronJobs" :key="job.name">
              <span>
                <span class="cron-name">{{ jobLabel(job) }}</span>
                <span class="cron-meta">{{ job.schedule }}  ·  {{ jobNextRun(job) }}</span>
              </span>
              <em :class="['source-badge', cronBadgeClass(job.last_status)]">{{ jobLastRun(job) }}</em>
            </div>
          </template>
          <div v-else><span>{{ t('activity.cronJobs') }}</span><em class="source-badge muted">{{ t('activity.loading') }}</em></div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useActivityMonitor } from "../view-models/useActivityMonitor";

const { monitor, currentLocale, t, monitorError, lastFetch, elapsed, historyHours, cpuColor, memColor, loadText, batteryText, cpuChartId, memChartId, apiHealth, API_HEALTH_ORDER, apiHealthOrdered, cronJobs, cronSummary, cronSummaryBadge, jobLabel, jobNextRun, jobLastRun, cronBadgeClass, fetchCronJobs, apiBadgeClass, fetchApiHealth, fmtGb, fmtPercent, pctWidth, fetchData, fetchSlowData, drawCharts } = useActivityMonitor();
</script>

<style scoped src="../styles/views/activity-monitor.css"></style>
