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
        <div v-if="loading" class="pipeline-empty">正在加载 Market Regime 计算链路...</div>
        <div v-else-if="payload" class="flow-canvas">
          <svg class="flow-arrows" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <marker id="pipeline-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto">
                <path d="M0 0 8 4 0 8Z" />
              </marker>
            </defs>
            <path d="M21 13H29" />
            <path d="M38 23V31" />
            <path d="M47 16C54 16 56 39 62 39" />
            <path d="M47 41C56 41 55 66 62 66" />
            <path d="M63 50V57" />
            <path d="M72 66H80" />
            <path d="M88 77V84" />
          </svg>

          <button
            v-for="node in payload.nodes"
            :key="node.id"
            class="flow-node"
            :class="[node.id, { active: selectedNodeId === node.id }, node.status]"
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

    <section v-if="payload" class="output-band glass-card">
      <article v-for="item in outputItems" :key="item.label">
        <span>{{ item.label }}</span>
        <strong :class="item.tone">{{ item.value }}</strong>
      </article>
      <article v-for="item in adaptiveItems" :key="item.label" class="adaptive">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, type MarketRegimePipelineResponse, type PipelineNode } from "../api";

const payload = ref<any | null>(null);
const selectedNodeId = ref("inputs");
const loading = ref(true);
const error = ref("");
const pipelines = ref<{ key: string; label: string; status: string }[]>([]);
const activeKey = ref("market_regime");

const currentLabel = computed(() => {
  const p = pipelines.value.find((p) => p.key === activeKey.value);
  return p ? `${p.label} Pipeline` : "Pipeline";
});

const selectedNode = computed<PipelineNode | null>(() => {
  const nodes = payload.value?.nodes || [];
  return nodes.find((node) => node.id === selectedNodeId.value) || nodes[0] || null;
});

const scoreText = computed(() => {
  const score = payload.value?.summary.score;
  return typeof score === "number" && Number.isFinite(score) ? score.toFixed(1) : "—";
});

const outputItems = computed(() => {
  if (!payload.value) return [];
  const summary = payload.value.summary;
  return [
    { label: "Confirmed", value: summary.confirmed_regime, tone: regimeClass(summary.confirmed_regime) },
    { label: "Raw", value: summary.raw_regime, tone: regimeClass(summary.raw_regime) },
    { label: "Score", value: Number(summary.score).toFixed(1), tone: "accent" },
    { label: "Method", value: summary.detection_method, tone: "accent" },
  ];
});

const adaptiveItems = computed(() => {
  const params = (payload.value?.summary?.adaptive_params || {}) as Record<string, string | number>;
  return Object.entries(params)
    .filter(([key]) => ["position_size", "max_positions", "stop_loss", "confidence_threshold"].includes(key))
    .map(([key, value]) => ({ label: paramLabel(key), value: formatParam(key, value) }));
});

function paramLabel(key: string) {
  return ({
    position_size: "Position",
    max_positions: "Max Pos",
    stop_loss: "Stop",
    confidence_threshold: "Signal Gate",
  } as Record<string, string>)[key] || key;
}

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
    if (!data.nodes.some((node: any) => node.id === selectedNodeId.value)) {
      selectedNodeId.value = data.nodes[0]?.id || "";
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
  grid-template-columns: repeat(4, minmax(128px, 1fr));
  grid-template-rows: repeat(4, 112px);
  gap: 24px;
  align-items: stretch;
}
.flow-arrows {
  position: absolute;
  inset: 12px 14px;
  width: calc(100% - 28px);
  height: calc(100% - 24px);
  pointer-events: none;
  overflow: visible;
}
.flow-arrows path {
  fill: none;
  stroke: rgba(0, 212, 255, 0.42);
  stroke-width: 0.55;
  filter: drop-shadow(0 0 4px rgba(0, 212, 255, 0.55));
  marker-end: url(#pipeline-arrow);
}
.flow-arrows marker path {
  fill: rgba(0, 212, 255, 0.8);
  stroke: none;
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
.inputs { grid-column: 1; grid-row: 1; }
.features { grid-column: 2; grid-row: 1; }
.rule_score { grid-column: 2; grid-row: 2; }
.hmm_inference { grid-column: 3; grid-row: 2; }
.hybrid_decision { grid-column: 3; grid-row: 3; }
.stability { grid-column: 4; grid-row: 3; }
.outputs { grid-column: 4; grid-row: 4; }
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
  grid-template-columns: repeat(8, minmax(0, 1fr));
  gap: 8px;
}
.output-band article {
  min-width: 0;
  padding: 10px 11px;
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
.adaptive strong {
  text-transform: none;
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
