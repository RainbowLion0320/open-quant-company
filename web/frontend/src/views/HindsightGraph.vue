<template>
  <div class="hindsight-graph view-page">
    <!-- 控制栏 -->
    <div class="graph-toolbar glass-card">
      <div class="toolbar-left">
        <h2 class="toolbar-title">{{ t('hindsight.title') }}</h2>
        <span class="toolbar-stats" v-if="stats">
          {{ t('hindsight.stats', { nodes: stats.total_nodes, links: stats.total_links || linkCount }) }}
        </span>
        <span class="toolbar-error" v-if="loadError">{{ loadError }}</span>
      </div>
      <div class="toolbar-right">
        <button
          class="btn-load"
          :class="{ loading: isLoading }"
          @click="loadGraph"
          :disabled="isLoading"
        >
          <span v-if="isLoading" class="btn-spinner" aria-hidden="true"></span>
          <svg v-else class="btn-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4" />
          </svg>
          {{ isLoading ? t('hindsight.fetching') : t('hindsight.loadGraph') }}
        </button>
      </div>
    </div>

    <!-- 3D 容器 -->
    <div class="graph-stage" ref="stageRef">
      <div ref="threeRef" class="three-container"></div>
      <div v-if="!graphLoaded && !isLoading" class="graph-placeholder glass-card">
        <span>{{ t('hindsight.standby') }}</span>
        <strong>{{ t('hindsight.waitLoad') }}</strong>
      </div>

      <!-- 悬浮提示 -->
      <div
        v-if="hoveredNode"
        class="node-tooltip glass-card"
        :style="tooltipStyle"
      >
        <div class="tip-badge" :class="hoveredNode.type">
          {{ hoveredNode.type.toUpperCase() }}
        </div>
        <p class="tip-text">{{ hoveredNode.fullText || hoveredNode.label }}</p>
        <div class="tip-meta" v-if="hoveredNode.entities?.length">
          <span class="tip-entity" v-for="e in hoveredNode.entities.slice(0, 6)" :key="e">{{ e }}</span>
        </div>
      </div>

      <!-- 详情面板 -->
      <transition name="panel-slide">
        <div v-if="selectedNode" class="detail-panel glass-card">
          <button class="panel-close" @click="deselectNode" :aria-label="t('hindsight.closeDetail')">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
          <div class="panel-header">
            <span class="panel-badge" :class="selectedNode.type">
              {{ selectedNode.type }}
            </span>
            <span class="panel-id">#{{ selectedNode.id?.slice(0, 8) }}</span>
            <span class="panel-degree">{{ t('hindsight.degree', { degree: selectedNode.degree || 0 }) }}</span>
          </div>
          <p class="panel-text">{{ selectedNode.fullText }}</p>
          <div class="panel-section" v-if="selectedNode.entities?.length">
            <h4>{{ t('hindsight.entities') }}</h4>
            <div class="chip-group">
              <span class="chip" v-for="e in selectedNode.entities" :key="e">{{ e }}</span>
            </div>
          </div>
          <div class="panel-section" v-if="selectedNode.tags?.length">
            <h4>{{ t('hindsight.tags') }}</h4>
            <div class="chip-group">
              <span class="chip tag-chip" v-for="t in selectedNode.tags" :key="t">{{ t }}</span>
            </div>
          </div>
          <div class="panel-meta">
            <div class="meta-row">
              <span>{{ t('hindsight.date') }}</span><strong>{{ fmtDate(selectedNode.date) }}</strong>
            </div>
            <div class="meta-row" v-if="selectedNode.proofCount > 1">
              <span>{{ t('hindsight.proofs') }}</span><strong>{{ selectedNode.proofCount }}</strong>
            </div>
          </div>
        </div>
      </transition>

      <!-- 图例 -->
      <div class="legend glass-card">
        <div class="legend-item"><span class="legend-dot obs"></span> {{ t('hindsight.observation') }}</div>
        <div class="legend-item"><span class="legend-dot exp"></span> {{ t('hindsight.experience') }}</div>
        <div class="legend-item"><span class="legend-dot wld"></span> {{ t('hindsight.world') }}</div>
        <div class="legend-item"><span class="legend-line sem"></span> {{ t('hindsight.semantic') }}</div>
        <div class="legend-item"><span class="legend-line tmp"></span> {{ t('hindsight.temporal') }}</div>
        <div class="legend-item"><span class="legend-line tag-l"></span> {{ t('hindsight.tag') }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useHindsightThreeGraph } from "../composables/useHindsightThreeGraph";
import { useI18n } from "../i18n";

const { t } = useI18n();
const {
  threeRef,
  stageRef,
  isLoading,
  graphLoaded,
  stats,
  hoveredNode,
  selectedNode,
  tooltipStyle,
  linkCount,
  loadError,
  loadGraph,
  deselectNode,
  fmtDate,
} = useHindsightThreeGraph(t);
</script>

<style scoped src="../styles/views/hindsight-graph.css"></style>
