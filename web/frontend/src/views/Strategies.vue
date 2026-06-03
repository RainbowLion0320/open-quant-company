<template>
  <div class="view-page">
    <!-- Static contract anchors: 策略目录 候选策略 生命周期 生产隔离 -->
    <div class="surface-toolbar">
      <div class="surface-copy">
        <span>{{ t('strategies.eyebrow') }}</span>
        <strong>{{ t('strategies.title') }}</strong>
        <small>{{ t('strategies.subtitle') }}</small>
      </div>
      <div class="surface-actions">
        <span v-if="loaded" class="text-2xs" style="color:var(--text-disabled)">{{ t('strategies.count', { count: catalog.length }) }}</span>
        <button @click="runAll" :disabled="store.running" class="btn btn-primary btn-sm">
          {{ store.running ? t('strategies.running', { progress: store.progress }) : t('strategies.runProduction') }}
        </button>
      </div>
    </div>

    <div class="isolation-banner">
      <strong>{{ t('strategies.isolationTitle') }}</strong>
      <span>{{ t('strategies.isolationBody') }}</span>
    </div>

    <div v-if="store.error" class="inline-alert danger">
      <span>{{ store.error }}</span>
      <button class="btn btn-xs" @click="reload">{{ t('common.retry') }}</button>
    </div>

    <div v-if="store.running" class="glass-card card-pad">
      <div class="text-xs mb-2" style="color:var(--text-secondary)">{{ store.progressMsg }}</div>
      <div class="progress-bar">
        <div class="progress-bar-fill" :style="{ width: store.progress + '%' }"></div>
      </div>
    </div>

    <div class="catalog-stats">
      <div v-for="card in statusCards" :key="card.key" class="glass-card catalog-stat">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </div>
    </div>

    <div class="catalog-controls glass-card">
      <label>
        <span>{{ t('strategies.lifecycle') }}</span>
        <select v-model="filters.lifecycle">
          <option value="">{{ t('common.all') }}</option>
          <option v-for="item in lifecycleOptions" :key="item" :value="item">{{ lifecycleLabel(item) }}</option>
        </select>
      </label>
      <label>
        <span>{{ t('strategies.type') }}</span>
        <select v-model="filters.strategyType">
          <option value="">{{ t('common.all') }}</option>
          <option v-for="item in typeOptions" :key="item" :value="item">{{ typeLabel(item) }}</option>
        </select>
      </label>
      <label>
        <span>{{ t('strategies.layer') }}</span>
        <select v-model="filters.layer">
          <option value="">{{ t('common.all') }}</option>
          <option v-for="item in layerOptions" :key="item" :value="item">{{ layerLabel(item) }}</option>
        </select>
      </label>
      <div class="evaluation-note">
        <span>{{ t('strategies.promotionNote', { count: evaluation?.baselines.length || 0 }) }}</span>
        <small>{{ evaluation?.status || 'research_required' }}</small>
      </div>
    </div>

    <div v-if="store.loading && !loaded" class="glass-card card-pad-lg empty-panel">
      {{ t('strategies.loading') }}
    </div>

    <div v-if="loaded && !filteredCatalog.length" class="glass-card card-pad-lg empty-panel">
      {{ t('strategies.emptyFiltered') }}
    </div>

    <div v-if="filteredCatalog.length" class="table-shell catalog-table-shell" style="--table-min:960px">
      <table class="data-table catalog-table">
        <colgroup>
          <col style="width:20%">
          <col style="width:12%">
          <col style="width:13%">
          <col style="width:14%">
          <col style="width:18%">
          <col style="width:12%">
          <col style="width:11%">
        </colgroup>
        <thead>
          <tr>
            <th>{{ t('common.strategy') }}</th>
            <th>{{ t('strategies.lifecycle') }}</th>
            <th>{{ t('strategies.type') }}</th>
            <th>{{ t('strategies.layer') }}</th>
            <th>{{ t('strategies.dataRequirements') }}</th>
            <th class="text-right">{{ t('strategies.latestScan') }}</th>
            <th class="text-right">{{ t('common.action') }}</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="item in filteredCatalog" :key="item.name">
            <tr>
              <td>
                <div class="strategy-cell">
                  <span class="strategy-dot" :style="{ background: colorFor(item.name), boxShadow: `0 0 8px ${colorFor(item.name)}` }"></span>
                  <div>
                    <strong>{{ item.label }}</strong>
                    <small>{{ item.name }}</small>
                  </div>
                </div>
              </td>
              <td><span :class="['status-badge', `status-${item.lifecycle}`]">{{ lifecycleLabel(item.lifecycle) }}</span></td>
              <td>{{ typeLabel(item.strategy_type) }}</td>
              <td>{{ layerLabel(item.layer) }}</td>
              <td>
                <div class="requirement-list">
                  <span v-for="req in item.data_requirements" :key="`${item.name}-${req}`">{{ req }}</span>
                </div>
              </td>
              <td class="text-right">
                <span class="scan-meta">{{ scanMeta(item.name) }}</span>
              </td>
              <td class="text-right">
                <div class="row-actions">
                  <button @click="toggleSignals(item.name)" class="btn btn-xs btn-ghost">{{ t('strategies.signals') }}</button>
                  <button @click="runCatalogStrategy(item)" :disabled="store.running" class="btn btn-xs">
                    {{ item.lifecycle === 'production' ? t('strategies.run') : t('strategies.researchScan') }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="currentStrategy === item.name" class="signal-row">
              <td colspan="7">
                <div v-if="signals.length" class="signal-preview">
                  <div v-for="sig in signals.slice(0, 10)" :key="`${item.name}-${sig.symbol}`" class="signal-chip">
                    <router-link :to="`/stocks/${sig.symbol}`">{{ sig.symbol }}</router-link>
                    <span>{{ sig.name }}</span>
                    <strong>{{ sig.score?.toFixed(1) }}</strong>
                    <em>{{ signalLabel(sig.signal) }}</em>
                  </div>
                </div>
                <div v-else class="signal-empty">{{ t('strategies.noSavedSignals') }}</div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <div v-if="governance" class="governance-panel glass-card">
      <div class="governance-header">
        <div>
          <span>{{ t('strategies.researchStack') }}</span>
          <strong>{{ t('strategies.researchLayering') }}</strong>
        </div>
        <div class="gate-chip">{{ t('strategies.paperGate', { sharpe: paperGateSharpe, drawdown: paperGateDrawdown }) }}</div>
      </div>
      <div class="role-grid">
        <div v-for="role in governance.roles" :key="role.name" class="role-card">
          <div class="role-title">
            <span :style="{ background: colorFor(role.name) }"></span>
            <strong>{{ labelFor(role.name) }}</strong>
          </div>
          <div class="role-layer">{{ layerLabel(role.layer) }}</div>
          <p>{{ role.primary_use }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useStrategiesView } from "../view-models/useStrategiesView";

const { store, t, currentStrategy, signals, loaded, catalog, governance, evaluation, filters, strategyColors, scanByName, filteredCatalog, lifecycleOptions, typeOptions, layerOptions, statusCards, paperGateSharpe, paperGateDrawdown, localizedStrategyLabel, lifecycleLabel, typeLabel, layerLabel, colorFor, labelFor, signalLabel, scanMeta, toggleSignals, runAll, runCatalogStrategy, reload, loadCatalog, loadGovernance, loadEvaluation } = useStrategiesView();
</script>

<style scoped src="../styles/views/strategies.css"></style>
