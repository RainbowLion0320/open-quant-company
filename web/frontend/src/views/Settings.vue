<template>
  <div class="view-page settings-page">
    <div class="surface-toolbar settings-action-bar">
      <div class="surface-copy">
        <span>{{ t('settings.eyebrow') }}</span>
        <strong>{{ t('settings.title') }}</strong>
        <small>{{ t('settings.subtitle') }}</small>
      </div>
      <div class="surface-actions">
        <button @click="saveWithConfirm" class="btn btn-primary btn-sm">{{ t('common.save') }}</button>
      </div>
    </div>

    <div v-if="saveError" class="inline-alert danger">
      <span>{{ saveError }}</span>
      <button class="btn btn-xs" @click="saveError = ''">{{ t('common.close') }}</button>
    </div>

    <!-- Session token -->
    <div class="glass-card card-pad-lg">
      <div class="section-heading mb-4">{{ t('settings.apiKey') }}</div>
      <div class="setting-row">
        <div>
          <strong>{{ t('settings.authStatus') }}</strong>
          <span>{{ apiKeyStatus }}</span>
        </div>
        <div style="display:flex;gap:8px;align-items:center;">
          <input
            v-model="apiKeyInput"
            type="password"
            :placeholder="t('settings.apiKeyPlaceholder')"
            class="key-input"
            @keyup.enter="saveApiKey"
          />
          <button @click="saveApiKey" class="btn btn-sm" :class="apiKeyInput ? 'btn-primary' : 'btn-muted'">{{ t('settings.set') }}</button>
        </div>
      </div>
    </div>

    <!-- Notification -->
    <div class="glass-card card-pad-lg">
      <div class="section-heading mb-4">{{ t('settings.telegram') }}</div>
      <div class="setting-row">
        <div>
          <strong>{{ t('settings.enableSignalPush') }}</strong>
          <span>{{ notificationText }}</span>
        </div>
        <button @click="toggleNotify"
          class="settings-toggle"
          :class="{ active: settings.trading?.notification?.enabled }"
          :aria-label="t('settings.toggleTelegram')">
          <span></span>
        </button>
      </div>
    </div>

    <!-- Data Sources -->
    <div class="glass-card card-pad-lg">
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
    <div class="glass-card card-pad-lg">
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
    <div class="glass-card card-pad-lg">
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

    <!-- Audit Log -->
    <div class="glass-card card-pad-lg">
      <div class="section-heading mb-4">{{ t('settings.audit') }}</div>
      <div class="source-list">
        <div v-for="entry in auditEntries" :key="entry.timestamp">
          <span>
            <span class="audit-time">{{ fmtAuditTime(entry.timestamp) }}</span>
            <span class="audit-summary">{{ entry.summary || entry.action || t('settings.configUpdate') }}</span>
          </span>
        </div>
        <div v-if="auditEntries.length === 0">
          <span>{{ t('settings.auditLog') }}</span>
          <span class="badge badge-muted">{{ t('settings.noRecords') }}</span>
        </div>
      </div>
    </div>

    <!-- Confirm Dialog -->
    <Teleport to="body">
      <div v-if="showConfirm" class="confirm-overlay" @click.self="cancelConfirm">
        <div class="confirm-box glass-card card-pad-lg">
          <h3>{{ t('settings.confirmTitle') }}</h3>
          <p>{{ t('settings.confirmBody') }}</p>
          <div class="confirm-actions">
            <button @click="cancelConfirm" class="btn btn-muted">{{ t('common.cancel') }}</button>
            <button @click="doSave" class="btn btn-primary">{{ t('settings.confirmSave') }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { useSettingsView } from "../view-models/useSettingsView";

const { currentLocale, t, settings, showConfirm, confirmSnapshot, apiKeyInput, strategyStatuses, auditEntries, saveError, apiKeyStatus, risk, hasRiskConfig, notificationText, sourceItems, fmtPct, fmtAuditTime, fetchStrategyStatuses, fetchAudit, sourceBadgeClass, statusBadgeClass, toggleNotify, saveWithConfirm, cloneConfig, restoreConfig, cancelConfirm, doSave, saveApiKey } = useSettingsView();
</script>

<style scoped src="../styles/views/settings.css"></style>
