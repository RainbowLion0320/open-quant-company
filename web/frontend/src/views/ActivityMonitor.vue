<template>
  <div class="system-page view-page">
    <!-- Static contract anchors: API HEALTH CRON JOBS Telegram -->

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

const { t, apiHealth, apiHealthOrdered, cronJobs, cronSummary, cronSummaryBadge, jobLabel, jobNextRun, jobLastRun, cronBadgeClass, apiBadgeClass } = useActivityMonitor();
</script>

<style scoped src="../styles/views/activity-monitor.css"></style>
