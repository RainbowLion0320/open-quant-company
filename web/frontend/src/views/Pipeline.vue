<template>
  <div class="view-page pipeline-page">
    <section class="pipeline-header glass-card">
      <div>
        <span class="eyebrow">Pipeline</span>
        <h1>{{ currentLabel }}</h1>
      </div>
      <div class="pipeline-selector" v-if="pipelines.length > 1">
        <button
          v-for="p in pipelines"
          :key="p.key"
          class="selector-btn"
          :class="{ active: activeKey === p.key }"
          @click="switchPipeline(p.key)"
        >
          {{ p.label }}
        </button>
      </div>
      <div class="pipeline-meta" v-if="payload && activeKey === 'market_regime'">
        <span :class="regimeClass(payload.summary.confirmed_regime)">{{ payload.summary.confirmed_regime }}</span>
        <strong>{{ scoreText }}</strong>
        <em>{{ payload.summary.detection_method }}</em>
      </div>
    </section>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="loadPipeline">重试</button>
    </div>

    <section class="pipeline-layout">
      <div class="flow-stage glass-card">
        <div v-if="loading" class="pipeline-empty">正在加载 Pipeline 数据...</div>
        <div v-else-if="payload" ref="canvasRef" class="flow-canvas" :style="canvasStyle">
          <!-- Arrow SVG overlay — viewBox matches canvas pixel size -->
          <svg
            v-if="arrowSvgPaths.length"
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
            <path
              v-for="(d, i) in arrowSvgPaths"
              :key="i"
              :d="d"
              fill="none"
              stroke="rgba(0, 212, 255, 0.45)"
              stroke-width="1.5"
              marker-end="url(#arrow-head)"
            />
          </svg>

          <button
            v-for="node in payload.nodes"
            :key="node.id"
            :ref="(el) => setNodeRef(node.id, el)"
            class="flow-node"
            :class="[{ active: selectedNodeId === node.id }, node.status]"
            :style="nodeStyle(node)"
            type="button"
            @click="selectedNodeId = node.id"
          >
            <span class="node-status"></span>
            <strong>{{ node.title }}</strong>
            <em>{{ node.subtitle }}</em>
            <div class="node-metrics">
              <span
                v-for="metric in node.metrics.slice(0, 3)"
                :key="`${node.id}-${metric.label}`"
                :class="metricClass(metric.tone)"
              >
                {{ metric.label }} <b>{{ metric.value }}</b>
              </span>
            </div>
          </button>
        </div>
        <div v-else class="pipeline-empty">暂无 Pipeline 数据</div>
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
            <h3>Inputs</h3>
            <span v-for="item in selectedNode.inputs" :key="item">{{ item }}</span>
          </div>
          <div>
            <h3>Outputs</h3>
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
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { api } from "../api";

interface PipelineNodeData {
  id: string;
  title: string;
  subtitle: string;
  status: string;
  metrics: any[];
  inputs: any[];
  outputs: any[];
}

const payload = ref<any | null>(null);
const selectedNodeId = ref("");
const loading = ref(true);
const error = ref("");
const pipelines = ref<{ key: string; label: string; status: string }[]>([]);
const activeKey = ref("market_regime");

// Node DOM refs for measuring positions
const nodeRefs = new Map<string, Element>();
const canvasRef = ref<HTMLElement | null>(null);
const canvasSize = reactive({ w: 800, h: 500 });
const arrowSvgPaths = ref<string[]>(function () { return []; }());

function setNodeRef(id: string, el: any) {
  if (el) nodeRefs.set(id, el.$el || el);
  else nodeRefs.delete(id);
}

const currentLabel = computed(() => {
  const p = pipelines.value.find((p) => p.key === activeKey.value);
  return p ? `${p.label} Pipeline` : "Pipeline";
});

const selectedNode = computed<PipelineNodeData | null>(() => {
  const nodes = payload.value?.nodes || [];
  return nodes.find((node: PipelineNodeData) => node.id === selectedNodeId.value) || nodes[0] || null;
});

const scoreText = computed(() => {
  const score = payload.value?.summary?.score;
  return typeof score === "number" && Number.isFinite(score) ? score.toFixed(1) : "—";
});

// ── Dynamic layout: topological depth, capped at 4 columns ──

const MAX_COLS = 4;

interface NodePos { col: number; row: number; id: string }

const nodeLayout = computed<NodePos[]>(() => {
  const nodes: PipelineNodeData[] = payload.value?.nodes || [];
  const edges: { source: string; target: string }[] = payload.value?.edges || [];
  if (!nodes.length) return [];

  const inDegree = new Map<string, number>();
  const children = new Map<string, string[]>();
  for (const n of nodes) {
    inDegree.set(n.id, 0);
    children.set(n.id, []);
  }
  for (const e of edges) {
    inDegree.set(e.target, (inDegree.get(e.target) || 0) + 1);
    children.get(e.source)?.push(e.target);
  }

  const rawDepth = new Map<string, number>();
  const queue: string[] = [];
  for (const n of nodes) {
    rawDepth.set(n.id, 0);
    if ((inDegree.get(n.id) || 0) === 0) queue.push(n.id);
  }
  while (queue.length) {
    const cur = queue.shift()!;
    for (const child of children.get(cur) || []) {
      rawDepth.set(child, Math.max(rawDepth.get(child) || 0, (rawDepth.get(cur) || 0) + 1));
      inDegree.set(child, (inDegree.get(child) || 0) - 1);
      if (inDegree.get(child) === 0) queue.push(child);
    }
  }

  const maxRaw = Math.max(...rawDepth.values(), 0);
  const depthRemap = new Map<string, number>();
  for (const n of nodes) {
    const raw = rawDepth.get(n.id) || 0;
    const col = maxRaw === 0 ? 0 : Math.round((raw / maxRaw) * (MAX_COLS - 1));
    depthRemap.set(n.id, col);
  }

  const colGroups = new Map<number, string[]>();
  for (const n of nodes) {
    const col = depthRemap.get(n.id) || 0;
    if (!colGroups.has(col)) colGroups.set(col, []);
    colGroups.get(col)!.push(n.id);
  }

  const positions: NodePos[] = [];
  for (const [col, ids] of [...colGroups.entries()].sort((a, b) => a[0] - b[0])) {
    ids.forEach((id, row) => positions.push({ col, row, id }));
  }
  return positions;
});

const numRows = computed(() => Math.max(...nodeLayout.value.map(p => p.row), 0) + 1);

const canvasStyle = computed(() => ({
  gridTemplateColumns: `repeat(${MAX_COLS}, minmax(128px, 1fr))`,
  gridTemplateRows: `repeat(${numRows.value}, 112px)`,
}));

function nodeStyle(node: PipelineNodeData) {
  const pos = nodeLayout.value.find(p => p.id === node.id);
  if (!pos) return {};
  return { gridColumn: pos.col + 1, gridRow: pos.row + 1 };
}

// ── Measure node positions and compute arrow SVG paths ──

function updateArrows() {
  const canvas = canvasRef.value;
  if (!canvas) { arrowSvgPaths.value = []; return; }

  const canvasRect = canvas.getBoundingClientRect();
  canvasSize.w = Math.round(canvasRect.width);
  canvasSize.h = Math.round(canvasRect.height);

  const edges: { source: string; target: string }[] = payload.value?.edges || [];
  const paths: string[] = [];

  for (const edge of edges) {
    const srcEl = nodeRefs.get(edge.source);
    const tgtEl = nodeRefs.get(edge.target);
    if (!srcEl || !tgtEl) continue;

    const srcRect = srcEl.getBoundingClientRect();
    const tgtRect = tgtEl.getBoundingClientRect();

    // Positions relative to canvas
    const x1 = srcRect.left + srcRect.width / 2 - canvasRect.left;
    const y1 = srcRect.bottom - canvasRect.top;
    const x2 = tgtRect.left + tgtRect.width / 2 - canvasRect.left;
    const y2 = tgtRect.top - canvasRect.top;

    if (Math.abs(x1 - x2) < 2) {
      // Same column: straight vertical
      paths.push(`M${x1} ${y1}L${x2} ${y2}`);
    } else {
      // Different columns: bezier curve
      const cy = (y1 + y2) / 2;
      paths.push(`M${x1} ${y1}C${x1} ${cy} ${x2} ${cy} ${x2} ${y2}`);
    }
  }
  arrowSvgPaths.value = paths;
}

// Re-measure arrows when payload changes or window resizes
watch(payload, () => nextTick(updateArrows), { deep: true });
watch(activeKey, () => nextTick(updateArrows));
onMounted(() => {
  window.addEventListener("resize", updateArrows);
});

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
      items.push({ label: k.replace(/_/g, " "), value: formatParam(k, v), tone: "accent" });
    }
  }
  return items;
});

// ── Helpers ──

function formatParam(key: string, value: string | number) {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value ?? "—");
  if (key === "position_size" || key === "stop_loss" || key === "confidence_threshold") {
    return `${(n * 100).toFixed(1)}%`;
  }
  return `${Math.round(n)}`;
}

function regimeClass(regime: string) {
  const v = String(regime || "").toLowerCase();
  if (v === "bull") return "positive";
  if (v === "bear") return "negative";
  if (v === "sideways") return "warning";
  return "neutral";
}

function metricClass(tone?: string) {
  return tone || "neutral";
}

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
    error.value = err?.message || "Pipeline 加载失败";
  } finally {
    loading.value = false;
  }
}

function switchPipeline(key: string) {
  activeKey.value = key;
  selectedNodeId.value = "";
  loadPipeline();
}

onMounted(async () => {
  try {
    const data = await api.pipelineList();
    pipelines.value = data.items || [];
  } catch {
    pipelines.value = [{ key: "market_regime", label: "Market Regime", status: "available" }];
  }
  loadPipeline();
});
</script>

<style scoped>
.pipeline-page {
  gap: 12px;
}
.pipeline-header {
  min-height: 76px;
  padding: 16px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.eyebrow {
  color: var(--accent);
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}
.pipeline-header h1 {
  margin-top: 4px;
  color: var(--text-primary);
  font-size: 23px;
  line-height: 1.1;
  font-weight: 680;
}
.pipeline-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: max-content;
}
.pipeline-meta span,
.pipeline-meta strong,
.pipeline-meta em {
  height: 28px;
  display: inline-flex;
  align-items: center;
  padding: 0 10px;
  border: 1px solid var(--border-default);
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.16);
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  font-style: normal;
  text-transform: uppercase;
}
.pipeline-meta strong {
  color: var(--accent);
}
.pipeline-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 12px;
  min-height: 600px;
}
.flow-stage,
.detail-panel,
.output-band {
  padding: 14px;
}
.flow-canvas {
  position: relative;
  min-height: 572px;
  display: grid;
  gap: 24px;
  align-items: stretch;
}
.flow-arrows {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  overflow: visible;
}
.flow-node {
  position: relative;
  z-index: 1;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-default);
  border-radius: 8px;
  background:
    linear-gradient(145deg, rgba(13, 26, 42, 0.94), rgba(6, 15, 28, 0.88)),
    radial-gradient(circle at 16% 12%, rgba(0, 212, 255, 0.12), transparent 42%);
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}
.flow-node:hover,
.flow-node.active {
  transform: translateY(-2px);
  border-color: rgba(0, 212, 255, 0.38);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.28), 0 0 18px rgba(0, 212, 255, 0.10);
}
.flow-node.active {
  background:
    linear-gradient(145deg, rgba(9, 31, 50, 0.98), rgba(11, 20, 38, 0.94)),
    radial-gradient(circle at 18% 12%, rgba(0, 212, 255, 0.18), transparent 44%);
}
.flow-node.fallback {
  border-color: rgba(234, 179, 8, 0.25);
}
.flow-node strong {
  display: block;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.15;
  font-weight: 680;
}
.flow-node em {
  display: block;
  margin-top: 5px;
  min-height: 30px;
  color: var(--text-tertiary);
  font-size: 10px;
  line-height: 1.35;
  font-style: normal;
}
.node-status {
  position: absolute;
  right: 11px;
  top: 11px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 10px rgba(0, 212, 255, 0.7);
}
.fallback .node-status {
  background: var(--warning);
  box-shadow: 0 0 10px rgba(234, 179, 8, 0.6);
}
.node-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}
.node-metrics span {
  max-width: 100%;
  padding: 2px 6px;
  border-radius: 5px;
  background: rgba(125, 211, 252, 0.06);
  color: var(--text-tertiary);
  font-size: 9px;
  line-height: 1.3;
  white-space: nowrap;
}
.node-metrics b {
  margin-left: 3px;
  color: var(--text-secondary);
  font-family: "JetBrains Mono", monospace;
  font-weight: 650;
}
.detail-panel {
  min-width: 0;
}
.panel-head.tight {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.panel-head.tight span {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 680;
}
.panel-head.tight small {
  color: var(--accent);
  font-family: "JetBrains Mono", monospace;
  font-size: 9px;
  text-transform: uppercase;
}
.detail-panel p {
  color: var(--text-tertiary);
  font-size: 11px;
  line-height: 1.5;
}
.detail-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
}
.detail-metrics div {
  min-width: 0;
  padding: 9px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.13);
}
.detail-metrics span,
.detail-lists h3,
.output-band span {
  display: block;
  color: var(--text-disabled);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.detail-metrics strong {
  display: block;
  margin-top: 3px;
  overflow: hidden;
  color: var(--text-secondary);
  font-family: "JetBrains Mono", monospace;
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.detail-lists {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}
.detail-lists div {
  display: grid;
  gap: 6px;
}
.detail-lists span,
.warning-stack span {
  display: block;
  padding: 7px 9px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.12);
  color: var(--text-secondary);
  font-size: 11px;
}
.warning-stack {
  display: grid;
  gap: 6px;
  margin-top: 14px;
}
.warning-stack span {
  border-color: rgba(234, 179, 8, 0.22);
  color: var(--warning);
}
.output-band {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}
.output-band article {
  min-width: 0;
  padding: 10px  11px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.12);
}
.output-band strong {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: var(--text-secondary);
  font-family: "JetBrains Mono", monospace;
  font-size: 13px;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}
.positive { color: var(--positive) !important; }
.negative { color: var(--negative) !important; }
.warning { color: var(--warning) !important; }
.accent { color: var(--accent) !important; }
.neutral { color: var(--text-secondary) !important; }
.pipeline-empty {
  min-height: 520px;
  display: grid;
  place-items: center;
  color: var(--text-tertiary);
  font-size: 12px;
}
.pipeline-selector {
  display: flex;
  gap: 4px;
  margin-top: 8px;
}
.selector-btn {
  padding: 4px 12px;
  border: 1px solid var(--border, #333);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary, #888);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.selector-btn:hover {
  background: var(--bg-hover, rgba(255,255,255,0.04));
}
.selector-btn.active {
  background: var(--accent-bg, rgba(99,102,241,0.15));
  border-color: var(--accent, #6366f1);
  color: var(--accent, #6366f1);
  font-weight: 600;
}

@media (max-width: 1180px) {
  .pipeline-layout {
    grid-template-columns: 1fr;
  }
  .detail-panel {
    min-height: auto;
  }
  .output-band {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .pipeline-header {
    align-items: flex-start;
    flex-direction: column;
  }
  .pipeline-meta {
    width: 100%;
    flex-wrap: wrap;
  }
  .flow-canvas {
    min-height: auto;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .flow-arrows {
    display: none;
  }
  .flow-node {
    min-height: 102px;
  }
  .detail-metrics,
  .output-band {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
