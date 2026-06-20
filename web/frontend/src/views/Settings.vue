<template>
  <div class="view-page settings-page">
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
                <span class="cron-meta">{{ job.schedule }} · {{ jobNextRun(job) }}</span>
              </span>
              <em :class="['source-badge', cronBadgeClass(job.last_status)]">{{ jobLastRun(job) }}</em>
            </div>
          </template>
          <div v-else><span>{{ t('activity.cronJobs') }}</span><em class="source-badge muted">{{ t('activity.loading') }}</em></div>
        </div>
      </div>
    </section>

    <section class="settings-config-grid">
      <!-- Session token -->
      <div class="glass-card settings-card">
        <div class="section-heading mb-4">{{ t('settings.apiKey') }}</div>
        <div class="setting-row">
          <div>
            <strong>{{ t('settings.authStatus') }}</strong>
            <span>{{ apiKeyStatus }}</span>
          </div>
        </div>
      </div>

      <!-- Notification -->
      <div class="glass-card settings-card">
        <div class="section-heading mb-4">{{ t('settings.telegram') }}</div>
        <div class="setting-row">
          <div>
            <strong>{{ t('settings.enableSignalPush') }}</strong>
            <span>{{ notificationText }}</span>
          </div>
          <span :class="['badge', settings.trading?.notification?.enabled ? 'badge-green' : 'badge-muted']">
            {{ settings.trading?.notification?.enabled ? t('common.enabled') : t('common.disabled') }}
          </span>
        </div>
      </div>

      <!-- Data Sources -->
      <div class="glass-card settings-card">
        <div class="section-heading mb-4">{{ t('settings.dataSources') }}</div>
        <div class="settings-list">
          <div v-for="src in sourceItems" :key="src.name">
            <span>{{ src.name }}</span>
            <span :class="['badge', sourceBadgeClass(src.status)]">{{ src.summary }}</span>
          </div>
          <div v-if="sourceItems.length === 0">
            <span>Registry</span>
            <span class="badge badge-muted">{{ t('settings.noConfig') }}</span>
          </div>
        </div>
      </div>

      <!-- Strategy Status -->
      <div class="glass-card settings-card">
        <div class="section-heading mb-4">{{ t('settings.strategyStatus') }}</div>
        <div class="settings-list">
          <div v-for="s in strategyStatuses" :key="s.name">
            <span>{{ s.label }}</span>
            <span :class="['badge', statusBadgeClass(s.status)]">{{ s.status_label }}</span>
          </div>
          <div v-if="strategyStatuses.length === 0">
            <span>{{ t('common.strategy') }}</span>
            <span class="badge badge-muted">{{ t('settings.strategyLoading') }}</span>
          </div>
        </div>
      </div>

      <!-- Risk Control -->
      <div class="glass-card settings-card">
        <div class="section-heading mb-4">{{ t('settings.riskControl') }}</div>
        <div class="settings-list">
          <div v-if="risk.max_single_position?.enabled">
            <span>{{ t('settings.maxSinglePosition') }}</span>
            <strong>{{ fmtPct(risk.max_single_position?.max_pct) }}</strong>
          </div>
          <div v-if="risk.max_total_exposure?.enabled">
            <span>{{ t('settings.maxTotalExposure') }}</span>
            <strong>{{ fmtPct(risk.max_total_exposure?.max_pct) }}</strong>
          </div>
          <div v-if="risk.max_orders_per_day?.enabled">
            <span>{{ t('settings.maxOrdersPerDay') }}</span>
            <strong>{{ risk.max_orders_per_day?.max_count ?? '—' }}</strong>
          </div>
          <div v-if="risk.max_drawdown_circuit_breaker?.enabled">
            <span>{{ t('settings.drawdownBreaker') }}</span>
            <strong>{{ fmtPct(risk.max_drawdown_circuit_breaker?.max_dd_pct) }}</strong>
          </div>
          <div v-if="!hasRiskConfig">
            <span>{{ t('settings.riskControl') }}</span>
            <span class="badge badge-muted">{{ t('settings.noRisk') }}</span>
          </div>
        </div>
      </div>

    </section>
  </div>
</template>

<script setup lang="ts">
import { useActivityMonitor } from "../view-models/useActivityMonitor";
import { useSettingsView } from "../view-models/useSettingsView";

const { t, settings, strategyStatuses, apiKeyStatus, risk, hasRiskConfig, notificationText, sourceItems, fmtPct, sourceBadgeClass, statusBadgeClass } = useSettingsView();
const { apiHealth, apiHealthOrdered, cronJobs, cronSummary, cronSummaryBadge, jobLabel, jobNextRun, jobLastRun, cronBadgeClass, apiBadgeClass } = useActivityMonitor();
</script>

<style scoped src="../styles/views/settings.css"></style>
