<template>
  <div class="view-page pipeline-page">
    <nav class="pipeline-tabs" v-if="pipelines.length > 1">
      <button
        v-for="p in pipelines"
        :key="p.key"
        class="tab-btn"
        :class="{ active: activeKey === p.key }"
        @click="switchPipeline(p.key)"
      >
        {{ p.label }}
      </button>
    </nav>

    <section class="pipeline-header glass-card">
      <div>
        <span class="eyebrow">{{ t('pipeline.eyebrow') }}</span>
        <h1>{{ currentLabel }}</h1>
      </div>
      <div class="pipeline-meta" v-if="payload && activeKey === 'market_regime'">
        <span :class="regimeClass(payload.summary.confirmed_regime)">{{ payload.summary.confirmed_regime }}</span>
        <strong>{{ scoreText }}</strong>
        <em>{{ payload.summary.detection_method }}</em>
      </div>
    </section>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="loadPipeline">{{ t('common.retry') }}</button>
    </div>

    <section class="pipeline-layout">
      <div ref="stageRef" class="flow-stage glass-card">
        <div v-if="loading" class="pipeline-empty">{{ t('pipeline.loading') }}</div>
        <div v-else-if="payload" ref="canvasRef" class="flow-canvas" :style="canvasStyle">
          <svg
            v-if="visibleArrowPaths.length"
            class="flow-arrows"
            :viewBox="`0 0 ${canvasSize.w} ${canvasSize.h}`"
            :width="canvasSize.w"
            :height="canvasSize.h"
            aria-hidden="true"
          >
            <defs>
              <marker id="arrow-head" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0 0 8 4 0 8Z" fill="rgba(0, 212, 255, 0.8)" />
              </marker>
            </defs>
            <g v-for="arrow in visibleArrowPaths" :key="arrow.id">
              <path
                :d="arrow.d"
                fill="none"
                :stroke="arrow.active ? 'rgba(0, 212, 255, 0.45)' : 'rgba(255, 255, 255, 0.45)'"
                :stroke-width="1.5"
                :stroke-dasharray="arrow.active ? 'none' : '4 3'"
                :marker-end="arrow.active ? 'url(#arrow-head)' : ''"
              />
              <path
                v-if="isSelectedEdge(arrow)"
                class="flow-edge-highlight"
                :d="arrow.d"
                fill="none"
                :stroke="arrow.active ? 'rgba(0, 212, 255, 0.95)' : 'rgba(255, 255, 255, 0.88)'"
                stroke-width="2.4"
                stroke-linecap="round"
                stroke-dasharray="7 9"
              />
              <text
                v-if="arrow.label"
                :x="arrow.labelX"
                :y="arrow.labelY"
                :fill="arrow.active ? 'rgba(0, 212, 255, 0.7)' : 'rgba(255, 255, 255, 0.62)'"
                font-size="8"
                text-anchor="middle"
                dominant-baseline="middle"
              >{{ arrow.label }}</text>
            </g>
          </svg>

          <button
            v-for="node in payload.nodes"
            :key="node.id"
            :ref="(el) => setNodeRef(node.id, el)"
            class="flow-node"
            :class="[{ active: selectedNodeId === node.id }, node.status, node.kind]"
            :style="nodeStyle(node)"
            type="button"
            @click="selectedNodeId = node.id"
          >
            <span class="node-status"></span>
            <strong>{{ node.title }}</strong>
            <em>{{ node.subtitle }}</em>
            <div class="node-metrics">
              <span
                v-for="metric in node.metrics"
                :key="`${node.id}-${metric.label}`"
                :class="metricClass(metric.tone)"
              >
                {{ metric.label }} <b>{{ metric.value }}</b>
              </span>
            </div>
          </button>
        </div>
        <div v-else class="pipeline-empty">{{ t('pipeline.empty') }}</div>
      </div>

      <aside class="detail-panel glass-card" v-if="selectedNode">
        <div class="panel-head tight">
          <span>{{ selectedNode.title }}</span>
          <small>{{ selectedNode.status }}</small>
        </div>
        <p>{{ selectedNode.subtitle }}</p>

        <div class="detail-metrics">
          <div v-for="metric in selectedNode.metrics" :key="metric.label">
            <span>{{ metric.label }}</span>
            <strong :class="metricClass(metric.tone)">{{ metric.value }}</strong>
          </div>
        </div>

        <div class="detail-lists">
          <div>
            <h3>{{ t('pipeline.inputs') }}</h3>
            <span v-for="item in selectedNode.inputs" :key="item">{{ item }}</span>
          </div>
          <div>
            <h3>{{ t('pipeline.outputs') }}</h3>
            <span v-for="item in selectedNode.outputs" :key="item">{{ item }}</span>
          </div>
        </div>

        <div v-if="payload?.warnings.length" class="warning-stack">
          <span v-for="warning in payload.warnings" :key="warning">{{ warning }}</span>
        </div>
      </aside>
    </section>

    <section v-if="payload && summaryItems.length" class="output-band glass-card">
      <article v-for="item in summaryItems" :key="item.label">
        <span>{{ item.label }}</span>
        <strong :class="item.tone">{{ item.value }}</strong>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { api } from "../api";
import { formatPipelineParam, metricClass, regimeClass } from "../composables/usePipelineData";
import { useI18n } from "../i18n";
import {
  layoutPipelineGraph,
  offsetPipelineEdgePath,
  visiblePipelineEdges,
  type PipelineEdgePath,
  type PipelineLayoutEdge,
  type PipelineNodePosition,
} from "../utils/pipelineLayout";

interface PipelineNodeData {
  id: string;
  title: string;
  subtitle: string;
  status: string;
  kind?: string;
  metrics: any[];
  inputs: any[];
  outputs: any[];
}

const payload = ref<any | null>(null);
const { t } = useI18n();
const selectedNodeId = ref("");
const loading = ref(true);
const error = ref("");
const pipelines = ref<{ key: string; label: string; status: string }[]>([]);
const activeKey = ref("market_regime");

const NODE_WIDTH = 176;
const CANVAS_PAD_X = 18;
const CANVAS_PAD_Y = 18;
const COMPACT_BREAKPOINT = 760;

// Node DOM refs for measuring adaptive node heights
const nodeRefs = new Map<string, Element>();
const stageRef = ref<HTMLElement | null>(null);
const canvasRef = ref<HTMLElement | null>(null);
const canvasSize = reactive({ w: 800, h: 500 });
const nodeSizes = ref<Record<string, { width: number; height: number }>>({});
const nodePositions = ref<Record<string, PipelineNodePosition>>({});
const arrowSvgPaths = ref<PipelineEdgePath[]>([]);
let layoutRunId = 0;
let layoutFrame = 0;

function setNodeRef(id: string, el: any) {
  if (el) nodeRefs.set(id, el.$el || el);
  else nodeRefs.delete(id);
}

const currentLabel = computed(() => {
  const p = pipelines.value.find((p) => p.key === activeKey.value);
  return p ? `${p.label} ${t("pipeline.titleSuffix")}` : t("pipeline.eyebrow");
});

const selectedNode = computed<PipelineNodeData | null>(() => {
  const nodes = payload.value?.nodes || [];
  return nodes.find((node: PipelineNodeData) => node.id === selectedNodeId.value) || nodes[0] || null;
});

const scoreText = computed(() => {
  const score = payload.value?.summary?.score;
  return typeof score === "number" && Number.isFinite(score) ? score.toFixed(1) : "—";
});

const canvasStyle = computed(() => ({
  width: `${canvasSize.w}px`,
  height: `${canvasSize.h}px`,
  minWidth: "100%",
}));

const visibleArrowPaths = computed(() => visiblePipelineEdges(arrowSvgPaths.value, selectedNodeId.value));

function isSelectedEdge(arrow: PipelineEdgePath) {
  return arrow.source === selectedNodeId.value || arrow.target === selectedNodeId.value;
}

function nodeStyle(node: PipelineNodeData) {
  const pos = nodePositions.value[node.id];
  if (!pos) return { opacity: 0 };
  return {
    left: `${pos.x}px`,
    top: `${pos.y}px`,
    width: `${pos.width}px`,
  };
}

// ── ELK layered layout with measured node heights ──

function schedulePipelineLayout() {
  if (layoutFrame) window.cancelAnimationFrame(layoutFrame);
  layoutFrame = window.requestAnimationFrame(() => {
    layoutFrame = 0;
    void updatePipelineLayout();
  });
}

async function updatePipelineLayout(allowMeasure = true) {
  const data = payload.value;
  if (loading.value || !data?.nodes?.length || !canvasRef.value) {
    arrowSvgPaths.value = [];
    return;
  }

  const runId = ++layoutRunId;
  const nodes: PipelineNodeData[] = data.nodes || [];
  const edges: PipelineLayoutEdge[] = data.edges || [];
  const stageWidth = Math.max(stageRef.value?.clientWidth || 800, 320);

  if (isCompactFlow()) {
    applyCompactLayout(nodes, stageWidth);
  } else {
    try {
      const result = await layoutPipelineGraph(
        nodes.map((node) => ({
          id: node.id,
          width: nodeSizes.value[node.id]?.width || NODE_WIDTH,
          height: nodeSizes.value[node.id]?.height || estimateNodeHeight(node),
        })),
        edges,
        { nodeSpacing: stageWidth < 1080 ? 18 : 34, layerSpacing: 118 },
      );
      if (runId !== layoutRunId) return;
      applyElkLayout(result, stageWidth);
    } catch (err) {
      console.error("Pipeline ELK layout failed", err);
      applyCompactLayout(nodes, stageWidth);
    }
  }

  await nextTick();
  if (allowMeasure && measureNodeSizes(nodes)) {
    await updatePipelineLayout(false);
  }
}

function applyElkLayout(
  result: { width: number; height: number; nodes: PipelineNodePosition[]; edges: PipelineEdgePath[] },
  stageWidth: number,
) {
  const layoutWidth = Math.max(Math.ceil(result.width), 1);
  const layoutHeight = Math.max(Math.ceil(result.height), 1);
  const canvasWidth = Math.max(layoutWidth + CANVAS_PAD_X * 2, stageWidth - 30, 320);
  const offsetX = Math.max(CANVAS_PAD_X, Math.round((canvasWidth - layoutWidth) / 2));
  const offsetY = CANVAS_PAD_Y;

  nodePositions.value = Object.fromEntries(result.nodes.map((node) => [
    node.id,
    {
      ...node,
      x: Math.round(node.x + offsetX),
      y: Math.round(node.y + offsetY),
    },
  ]));
  arrowSvgPaths.value = result.edges
    .filter((edge) => edge.d)
    .map((edge) => offsetPipelineEdgePath(edge, offsetX, offsetY))
    .sort((a, b) => Number(a.active) - Number(b.active));
  canvasSize.w = Math.round(canvasWidth);
  canvasSize.h = Math.max(layoutHeight + CANVAS_PAD_Y * 2, 240);
}

function applyCompactLayout(nodes: PipelineNodeData[], stageWidth: number) {
  const canvasWidth = Math.max(stageWidth - 30, 260);
  const x = Math.max(14, Math.round((canvasWidth - NODE_WIDTH) / 2));
  let y = CANVAS_PAD_Y;
  const positions: Record<string, PipelineNodePosition> = {};

  for (const node of nodes) {
    const height = nodeSizes.value[node.id]?.height || estimateNodeHeight(node);
    positions[node.id] = { id: node.id, x, y, width: NODE_WIDTH, height };
    y += height + 18;
  }

  nodePositions.value = positions;
  arrowSvgPaths.value = [];
  canvasSize.w = Math.round(canvasWidth);
  canvasSize.h = Math.max(y + CANVAS_PAD_Y, 240);
}

function estimateNodeHeight(node: PipelineNodeData) {
  const metrics = node.metrics?.length || 0;
  const metricRows = Math.max(1, Math.ceil(metrics / 2));
  const subtitleRows = Math.max(1, Math.ceil(String(node.subtitle || "").length / 38));
  return Math.max(112, 54 + subtitleRows * 13 + metricRows * 17);
}

function measureNodeSizes(nodes: PipelineNodeData[]) {
  let changed = false;
  const nextSizes = { ...nodeSizes.value };

  for (const node of nodes) {
    const el = nodeRefs.get(node.id) as HTMLElement | undefined;
    if (!el) continue;

    const width = NODE_WIDTH;
    const height = Math.max(96, Math.ceil(el.getBoundingClientRect().height));
    const previous = nextSizes[node.id];
    if (!previous || Math.abs(previous.height - height) > 1 || Math.abs(previous.width - width) > 1) {
      nextSizes[node.id] = { width, height };
      changed = true;
    }
  }

  if (changed) nodeSizes.value = nextSizes;
  return changed;
}

function isCompactFlow() {
  return window.innerWidth <= COMPACT_BREAKPOINT;
}

watch(payload, () => nextTick(schedulePipelineLayout), { deep: true });
watch(loading, () => nextTick(schedulePipelineLayout));

// ── Dynamic summary output band ──

const summaryItems = computed(() => {
  if (!payload.value) return [];
  const summary = payload.value.summary || {};
  const skip = new Set(["adaptive_params"]);
  const items: { label: string; value: string; tone: string }[] = [];
  for (const [key, val] of Object.entries(summary)) {
    if (skip.has(key)) continue;
    if (val === null || val === undefined) continue;
    const displayVal = typeof val === "number"
      ? (Number.isFinite(val) ? (Math.abs(val) < 1 ? val.toFixed(4) : val.toFixed(1)) : "—")
      : String(val);
    items.push({ label: key.replace(/_/g, " "), value: displayVal, tone: "neutral" });
  }
  const params = summary.adaptive_params;
  if (params && typeof params === "object") {
    for (const [k, v] of Object.entries(params as Record<string, any>)) {
      items.push({ label: k.replace(/_/g, " "), value: formatPipelineParam(k, v), tone: "accent" });
    }
  }
  return items;
});

async function loadPipeline() {
  loading.value = true;
  error.value = "";
  try {
    const data = await api.pipelineShow(activeKey.value);
    payload.value = data;
    if (!data.nodes?.some((node: any) => node.id === selectedNodeId.value)) {
      selectedNodeId.value = data.nodes?.[0]?.id || "";
    }
  } catch (err: any) {
    error.value = err?.message || t("pipeline.retryError");
  } finally {
    loading.value = false;
  }
}

function switchPipeline(key: string) {
  activeKey.value = key;
  selectedNodeId.value = "";
  nodeSizes.value = {};
  nodePositions.value = {};
  arrowSvgPaths.value = [];
  loadPipeline();
}

onMounted(async () => {
  window.addEventListener("resize", schedulePipelineLayout);
  try {
    const data = await api.pipelineList();
    pipelines.value = data.items || [];
  } catch {
    pipelines.value = [{ key: "market_regime", label: "Market Regime", status: "available" }];
  }
  loadPipeline();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", schedulePipelineLayout);
  if (layoutFrame) window.cancelAnimationFrame(layoutFrame);
});
</script>

<style scoped>
/* pipeline-flow stroke-dashoffset */
</style>
<style scoped src="../styles/views/pipeline.css"></style>
