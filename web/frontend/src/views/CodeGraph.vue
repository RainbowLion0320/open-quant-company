<template>
  <div class="codegraph view-page">
    <div class="graph-toolbar glass-card">
      <div class="toolbar-left">
        <h2 class="toolbar-title">{{ t("codegraph.title") }}</h2>
        <span class="toolbar-stats" v-if="stats">
          {{ t("codegraph.stats", { files: stats.file_count, nodes: stats.node_count, edges: stats.edge_count }) }}
        </span>
        <span class="status-pill" :class="{ stale: status?.stale, missing: !status?.initialized }">
          {{ status?.initialized ? (status.stale ? t("codegraph.stale") : t("codegraph.current")) : t("codegraph.missing") }}
        </span>
        <span class="toolbar-error" v-if="loadError">{{ loadError }}</span>
      </div>
      <div class="toolbar-right">
        <div class="search-box">
          <input
            v-model="searchQuery"
            :placeholder="t('codegraph.search')"
            @keyup.enter="runSearch"
          />
          <button class="icon-button" @click="runSearch" :aria-label="t('codegraph.searchAction')">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z" /></svg>
          </button>
          <div v-if="searchResults.length" class="search-results glass-card">
            <button v-for="item in searchResults" :key="item.id" @click="openSearchResult(item)">
              <strong>{{ item.label }}</strong>
              <span>{{ item.kind }} · {{ item.path }}</span>
            </button>
          </div>
        </div>
        <div class="level-control">
          <button :class="{ active: level === 'module' }" @click="loadGraph('module', '')">{{ t("codegraph.modules") }}</button>
          <button :class="{ active: level === 'file' }" :disabled="!root" @click="loadGraph('file', root)">{{ t("codegraph.files") }}</button>
          <button :class="{ active: level === 'symbol' }" :disabled="!root" @click="loadGraph('symbol', root)">{{ t("codegraph.symbols") }}</button>
        </div>
        <button class="btn-load" :class="{ loading: isLoading }" @click="loadGraph(level, root)" :disabled="isLoading">
          <span v-if="isLoading" class="btn-spinner" aria-hidden="true"></span>
          <svg v-else class="btn-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4" />
          </svg>
          {{ t("codegraph.refresh") }}
        </button>
        <button class="btn-load" @click="syncIndex('sync')" :disabled="isSyncing">{{ isSyncing ? t("codegraph.syncing") : t("codegraph.sync") }}</button>
        <button class="btn-load danger" @click="syncIndex('rebuild')" :disabled="isSyncing">{{ t("codegraph.rebuild") }}</button>
      </div>
    </div>

    <div class="graph-subbar glass-card">
      <div class="breadcrumb">
        <button v-for="item in breadcrumb" :key="`${item.level}:${item.root}`" @click="loadGraph(item.level, item.root)">
          {{ item.label }}
        </button>
      </div>
      <div class="edge-filters">
        <button
          v-for="kind in edgeKinds"
          :key="kind"
          :class="{ active: selectedEdges.includes(kind) }"
          @click="toggleEdgeKind(kind)"
        >
          {{ kind }}
        </button>
      </div>
    </div>

    <div class="graph-stage" ref="stageRef">
      <div ref="threeRef" class="three-container"></div>
      <div v-if="!graphLoaded && !isLoading" class="graph-placeholder glass-card">
        <span>{{ t("codegraph.standby") }}</span>
        <strong>{{ t("codegraph.waitLoad") }}</strong>
      </div>

      <div v-if="hoveredNode" class="node-tooltip glass-card" :style="tooltipStyle">
        <div class="tip-badge" :class="hoveredNode.kind">{{ hoveredNode.kind.toUpperCase() }}</div>
        <p class="tip-text">{{ hoveredNode.qualified_name || hoveredNode.label }}</p>
        <div class="tip-meta">
          <span class="tip-entity">{{ hoveredNode.path }}</span>
          <span class="tip-entity">{{ t("codegraph.degree", { degree: hoveredNode.degree || 0 }) }}</span>
        </div>
      </div>

      <transition name="panel-slide">
        <div v-if="selectedNode" class="detail-panel glass-card">
          <button class="panel-close" @click="deselectNode" :aria-label="t('codegraph.closeDetail')">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
          <div class="panel-header">
            <span class="panel-badge" :class="selectedNode.kind">{{ selectedNode.kind }}</span>
            <span class="panel-degree">{{ t("codegraph.degree", { degree: selectedNode.degree || 0 }) }}</span>
          </div>
          <p class="panel-title">{{ selectedNode.qualified_name || selectedNode.label }}</p>
          <div class="panel-meta">
            <div class="meta-row"><span>{{ t("codegraph.path") }}</span><strong>{{ selectedNode.path }}</strong></div>
            <div class="meta-row"><span>{{ t("codegraph.language") }}</span><strong>{{ selectedNode.language }}</strong></div>
            <div class="meta-row"><span>{{ t("codegraph.lines") }}</span><strong>{{ lineRange(selectedNode) }}</strong></div>
            <div class="meta-row"><span>{{ t("codegraph.count") }}</span><strong>{{ selectedNode.count }}</strong></div>
          </div>
          <div class="panel-section" v-if="selectedNode.signature">
            <h4>{{ t("codegraph.signature") }}</h4>
            <p>{{ selectedNode.signature }}</p>
          </div>
          <div class="panel-section" v-if="selectedNode.docstring">
            <h4>{{ t("codegraph.docstring") }}</h4>
            <p>{{ selectedNode.docstring }}</p>
          </div>
        </div>
      </transition>

      <div class="legend glass-card">
        <div class="legend-item"><span class="legend-dot module"></span>{{ t("codegraph.module") }}</div>
        <div class="legend-item"><span class="legend-dot file"></span>{{ t("codegraph.file") }}</div>
        <div class="legend-item"><span class="legend-dot symbol"></span>{{ t("codegraph.symbol") }}</div>
        <div class="legend-item"><span class="legend-line inbound"></span>{{ t("codegraph.inbound") }}</div>
        <div class="legend-item"><span class="legend-line outbound"></span>{{ t("codegraph.outbound") }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useCodeGraph } from "../composables/useCodeGraph";
import { useI18n } from "../i18n";

const { t } = useI18n();
const {
  threeRef,
  stageRef,
  isLoading,
  isSyncing,
  graphLoaded,
  level,
  root,
  status,
  stats,
  hoveredNode,
  selectedNode,
  tooltipStyle,
  loadError,
  searchQuery,
  searchResults,
  selectedEdges,
  edgeKinds,
  breadcrumb,
  loadGraph,
  runSearch,
  openSearchResult,
  syncIndex,
  toggleEdgeKind,
  deselectNode,
  lineRange,
} = useCodeGraph(t);
</script>

<style scoped src="../styles/views/codegraph.css"></style>
