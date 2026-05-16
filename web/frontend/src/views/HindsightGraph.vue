<template>
  <div class="hindsight-graph">
    <!-- 控制栏 -->
    <div class="graph-toolbar glass-card">
      <div class="toolbar-left">
        <h2 class="toolbar-title">HINDSIGHT KNOWLEDGE GRAPH</h2>
        <span class="toolbar-stats" v-if="stats">
          {{ stats.total_nodes }} NODES · {{ stats.total_links || linkCount }} LINKS
        </span>
      </div>
      <div class="toolbar-right">
        <button
          class="btn-load"
          :class="{ loading: isLoading }"
          @click="loadGraph"
          :disabled="isLoading"
        >
          <span class="btn-icon">{{ isLoading ? '◈' : '⟳' }}</span>
          {{ isLoading ? 'FETCHING...' : 'LOAD GRAPH' }}
        </button>
      </div>
    </div>

    <!-- 图谱画布 -->
    <div class="graph-stage" ref="stageRef">
      <canvas ref="canvasRef" class="graph-canvas"></canvas>

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
          <button class="panel-close" @click="selectedNode = null">✕</button>
          <div class="panel-header">
            <span class="panel-badge" :class="selectedNode.type">
              {{ selectedNode.type }}
            </span>
            <span class="panel-id">#{{ selectedNode.id?.slice(0, 8) }}</span>
          </div>
          <p class="panel-text">{{ selectedNode.fullText }}</p>
          <div class="panel-section" v-if="selectedNode.entities?.length">
            <h4>ENTITIES</h4>
            <div class="chip-group">
              <span class="chip" v-for="e in selectedNode.entities" :key="e">{{ e }}</span>
            </div>
          </div>
          <div class="panel-section" v-if="selectedNode.tags?.length">
            <h4>TAGS</h4>
            <div class="chip-group">
              <span class="chip tag-chip" v-for="t in selectedNode.tags" :key="t">{{ t }}</span>
            </div>
          </div>
          <div class="panel-meta">
            <div class="meta-row">
              <span>Date</span><strong>{{ fmtDate(selectedNode.date) }}</strong>
            </div>
            <div class="meta-row" v-if="selectedNode.proofCount > 1">
              <span>Proofs</span><strong>{{ selectedNode.proofCount }}</strong>
            </div>
          </div>
        </div>
      </transition>

      <!-- 图例 -->
      <div class="legend glass-card">
        <div class="legend-item"><span class="legend-dot obs"></span> Observation</div>
        <div class="legend-item"><span class="legend-dot exp"></span> Experience</div>
        <div class="legend-item"><span class="legend-line sem"></span> Semantic</div>
        <div class="legend-item"><span class="legend-line tmp"></span> Temporal</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, computed } from "vue";

interface GraphNode {
  id: string; index: number; label: string; fullText: string;
  type: "observation" | "experience"; entities: string[]; tags: string[];
  date: string; documentId: string | null; chunkId: string | null;
  consolidatedAt: string | null; proofCount: number;
  x?: number; y?: number; vx?: number; vy?: number;
}

interface GraphLink {
  source: number | GraphNode; target: number | GraphNode;
  type: string; label: string;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  stats?: { total_nodes: number; total_links: number; last_consolidated: string };
}

interface SimNode extends GraphNode {
  x: number; y: number; vx: number; vy: number; fx?: number | null; fy?: number | null;
}

const canvasRef = ref<HTMLCanvasElement | null>(null);
const stageRef = ref<HTMLElement | null>(null);
const isLoading = ref(false);
const stats = ref<GraphData["stats"] | null>(null);
const hoveredNode = ref<GraphNode | null>(null);
const selectedNode = ref<GraphNode | null>(null);
const tooltipStyle = ref({ left: "0px", top: "0px" });
const linkCount = ref(0);

let simNodes: SimNode[] = [];
let simLinks: { source: SimNode; target: SimNode; type: string }[] = [];
let animFrame = 0;
let canvasCtx: CanvasRenderingContext2D | null = null;
let dpr = 1;
let transform = { x: 0, y: 0, scale: 1 };
let isDragging = false;
let dragTarget: SimNode | null = null;
let dragStart = { x: 0, y: 0 };
let lastMouse = { x: 0, y: 0 };

// ── Colors ──
const COLORS = {
  bg: "#02060d",
  obs: "#00d4ff",
  obsGlow: "rgba(0,212,255,0.25)",
  exp: "#7c3aed",
  expGlow: "rgba(124,58,237,0.25)",
  semantic: "rgba(0,212,255,0.35)",
  temporal: "rgba(148,163,184,0.15)",
  tag: "rgba(124,58,237,0.12)",
  consolidation: "rgba(0,255,200,0.2)",
  text: "#e2e8f0",
  textDim: "#64748b",
  grid: "rgba(0,212,255,0.03)",
};

function fmtDate(d: string): string {
  if (!d) return "—";
  return d.slice(0, 10);
}

async function loadGraph() {
  isLoading.value = true;
  try {
    const res = await fetch("/api/hindsight/graph");
    const data: GraphData = await res.json();
    stats.value = data.stats || null;
    linkCount.value = data.links?.length || 0;
    initSimulation(data.nodes, data.links);
  } catch (e) {
    console.error("Failed to load graph:", e);
  } finally {
    isLoading.value = false;
  }
}

function initSimulation(nodes: GraphNode[], links: GraphLink[]) {
  const w = canvasRef.value!.width / dpr;
  const h = canvasRef.value!.height / dpr;
  const cx = w / 2;
  const cy = h / 2;

  simNodes = nodes.map((n) => ({
    ...n,
    x: cx + (Math.random() - 0.5) * w * 0.3,
    y: cy + (Math.random() - 0.5) * h * 0.3,
    vx: 0,
    vy: 0,
  }));

  simLinks = links.map((l) => ({
    source: simNodes[typeof l.source === "number" ? l.source : (l.source as GraphNode).index],
    target: simNodes[typeof l.target === "number" ? l.target : (l.target as GraphNode).index],
    type: l.type,
  }));

  transform = { x: 0, y: 0, scale: 1 };
  selectedNode.value = null;
  hoveredNode.value = null;

  // Kick off the animation loop
  cancelAnimationFrame(animFrame);
  animFrame = requestAnimationFrame(tick);
}

function tick() {
  const alpha = 0.03;
  const centering = 0.002;
  const damping = 0.92;
  const repulsion = 600;
  const springLen = 120;
  const springK = 0.02;

  const w = canvasRef.value!.width / dpr;
  const h = canvasRef.value!.height / dpr;

  for (const n of simNodes) {
    if (n.fx != null) continue;
    // Repulsion
    for (const m of simNodes) {
      if (n === m) continue;
      let dx = n.x - m.x;
      let dy = n.y - m.y;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
      const force = repulsion / (dist * dist);
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      n.vx += fx;
      n.vy += fy;
    }
    // Centering
    n.vx += (w / 2 - n.x) * centering;
    n.vy += (h / 2 - n.y) * centering;
    // Damping
    n.vx *= damping;
    n.vy *= damping;
    n.x += n.vx;
    n.y += n.vy;
    // Bounds
    n.x = Math.max(50, Math.min(w - 50, n.x));
    n.y = Math.max(50, Math.min(h - 50, n.y));
  }

  // Spring forces
  for (const l of simLinks) {
    const s = l.source as SimNode;
    const t = l.target as SimNode;
    let dx = t.x - s.x;
    let dy = t.y - s.y;
    const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
    const displacement = (dist - springLen) * springK;
    const fx = (dx / dist) * displacement;
    const fy = (dy / dist) * displacement;
    if (s.fx == null) { s.vx += fx; s.vy += fy; }
    if (t.fx == null) { t.vx -= fx; t.vy -= fy; }
  }

  draw();
  animFrame = requestAnimationFrame(tick);
}

function draw() {
  const canvas = canvasRef.value!;
  const ctx = canvasCtx!;
  const w = canvas.width / dpr;
  const h = canvas.height / dpr;

  ctx.save();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  // Background grid
  ctx.strokeStyle = COLORS.grid;
  ctx.lineWidth = 0.5;
  const gs = 60;
  const ox = ((transform.x / transform.scale) % gs + gs) % gs;
  const oy = ((transform.y / transform.scale) % gs + gs) % gs;
  for (let x = -ox; x < w; x += gs) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
  }
  for (let y = -oy; y < h; y += gs) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }

  ctx.translate(transform.x, transform.y);
  ctx.scale(transform.scale, transform.scale);

  // Links
  for (const l of simLinks) {
    const s = l.source as SimNode;
    const t = l.target as SimNode;
    ctx.beginPath();
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(t.x, t.y);

    if (l.type === "semantic") {
      ctx.strokeStyle = COLORS.semantic;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 6]);
    } else if (l.type === "temporal") {
      ctx.strokeStyle = COLORS.temporal;
      ctx.lineWidth = 0.5;
      ctx.setLineDash([]);
    } else if (l.type === "consolidation") {
      ctx.strokeStyle = COLORS.consolidation;
      ctx.lineWidth = 1.5;
      ctx.setLineDash([2, 3]);
    } else {
      ctx.strokeStyle = COLORS.tag;
      ctx.lineWidth = 0.5;
      ctx.setLineDash([1, 4]);
    }
    ctx.stroke();
  }
  ctx.setLineDash([]);

  // Nodes
  for (const n of simNodes) {
    const r = n.type === "experience" ? 8 : 5.5;
    const isHovered = hoveredNode.value?.id === n.id;
    const isSelected = selectedNode.value?.id === n.id;

    // Glow ring
    ctx.beginPath();
    ctx.arc(n.x, n.y, r + 8 + (isHovered ? 4 : 0), 0, Math.PI * 2);
    const glow = ctx.createRadialGradient(n.x, n.y, r * 0.5, n.x, n.y, r + 10);
    const glowColor = n.type === "experience" ? COLORS.expGlow : COLORS.obsGlow;
    glow.addColorStop(0, glowColor);
    glow.addColorStop(1, "transparent");
    ctx.fillStyle = glow;
    ctx.fill();

    // Core circle
    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
    ctx.fillStyle = n.type === "experience" ? COLORS.exp : COLORS.obs;
    if (isHovered || isSelected) {
      ctx.shadowColor = n.type === "experience" ? COLORS.exp : COLORS.obs;
      ctx.shadowBlur = 18;
    }
    ctx.fill();
    ctx.shadowBlur = 0;

    // Selection ring
    if (isSelected) {
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + 5, 0, Math.PI * 2);
      ctx.strokeStyle = n.type === "experience" ? COLORS.exp : COLORS.obs;
      ctx.lineWidth = 2;
      ctx.stroke();
    }

  }

  ctx.restore();
}

function screenToWorld(ex: number, ey: number): { x: number; y: number } {
  const rect = canvasRef.value!.getBoundingClientRect();
  const sx = ex - rect.left;
  const sy = ey - rect.top;
  return {
    x: (sx - transform.x) / transform.scale,
    y: (sy - transform.y) / transform.scale,
  };
}

function findNodeAt(wx: number, wy: number): SimNode | null {
  const hitRadius = 14;
  for (const n of simNodes) {
    const dx = n.x - wx;
    const dy = n.y - wy;
    if (dx * dx + dy * dy < hitRadius * hitRadius) return n;
  }
  return null;
}

function onMouseDown(e: MouseEvent) {
  const world = screenToWorld(e.clientX, e.clientY);
  const node = findNodeAt(world.x, world.y);
  if (node) {
    dragTarget = node;
    node.fx = node.x;
    node.fy = node.y;
    isDragging = true;
    dragStart = { x: e.clientX, y: e.clientY };
  } else {
    dragTarget = null;
    isDragging = true;
    dragStart = { x: e.clientX - transform.x, y: e.clientY - transform.y };
    lastMouse = { x: e.clientX, y: e.clientY };
  }
}

function onMouseMove(e: MouseEvent) {
  if (isDragging && dragTarget) {
    const world = screenToWorld(e.clientX, e.clientY);
    dragTarget.fx = world.x;
    dragTarget.fy = world.y;
  } else if (isDragging) {
    transform.x = e.clientX - dragStart.x;
    transform.y = e.clientY - dragStart.y;
  } else {
    const world = screenToWorld(e.clientX, e.clientY);
    const node = findNodeAt(world.x, world.y);
    if (node) {
      hoveredNode.value = {
        id: node.id, index: node.index, label: node.label, fullText: node.fullText,
        type: node.type, entities: node.entities, tags: node.tags, date: node.date,
        documentId: node.documentId || null, chunkId: node.chunkId || null,
        consolidatedAt: node.consolidatedAt || null, proofCount: node.proofCount,
      };
      tooltipStyle.value = {
        left: `${e.clientX + 14}px`,
        top: `${e.clientY - 10}px`,
      };
    } else {
      hoveredNode.value = null;
    }
    canvasRef.value!.style.cursor = node ? "pointer" : "grab";
  }
}

function onMouseUp(e: MouseEvent) {
  if (dragTarget) {
    // If barely moved, treat as click
    const dx = e.clientX - dragStart.x;
    const dy = e.clientY - dragStart.y;
    if (Math.abs(dx) < 3 && Math.abs(dy) < 3) {
      selectedNode.value = {
        id: dragTarget.id, index: dragTarget.index, label: dragTarget.label,
        fullText: dragTarget.fullText, type: dragTarget.type,
        entities: dragTarget.entities, tags: dragTarget.tags, date: dragTarget.date,
        documentId: dragTarget.documentId || null, chunkId: dragTarget.chunkId || null,
        consolidatedAt: dragTarget.consolidatedAt || null, proofCount: dragTarget.proofCount,
      };
    } else {
      // Release drag
      dragTarget.fx = null;
      dragTarget.fy = null;
    }
  }
  dragTarget = null;
  isDragging = false;
  canvasRef.value!.style.cursor = "grab";
}

function onWheel(e: WheelEvent) {
  e.preventDefault();
  const delta = e.deltaY > 0 ? 0.9 : 1.1;
  const newScale = Math.max(0.2, Math.min(3, transform.scale * delta));
  const rect = canvasRef.value!.getBoundingClientRect();
  const mx = e.clientX - rect.left;
  const my = e.clientY - rect.top;
  transform.x -= (mx - transform.x) * (newScale / transform.scale - 1);
  transform.y -= (my - transform.y) * (newScale / transform.scale - 1);
  transform.scale = newScale;
}

function resizeCanvas() {
  const stage = stageRef.value;
  if (!stage || !canvasRef.value) return;
  dpr = window.devicePixelRatio || 1;
  const w = stage.clientWidth;
  const h = stage.clientHeight;
  canvasRef.value.width = w * dpr;
  canvasRef.value.height = h * dpr;
  canvasRef.value.style.width = `${w}px`;
  canvasRef.value.style.height = `${h}px`;
  canvasCtx = canvasRef.value.getContext("2d")!;
}

onMounted(async () => {
  resizeCanvas();
  window.addEventListener("resize", resizeCanvas);

  const canvas = canvasRef.value!;
  canvas.addEventListener("mousedown", onMouseDown);
  canvas.addEventListener("mousemove", onMouseMove);
  canvas.addEventListener("mouseup", onMouseUp);
  canvas.addEventListener("wheel", onWheel, { passive: false });
  canvas.style.cursor = "grab";

  await loadGraph();
});

onUnmounted(() => {
  cancelAnimationFrame(animFrame);
  window.removeEventListener("resize", resizeCanvas);
});
</script>

<style scoped>
.hindsight-graph {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 12px;
}

/* Toolbar */
.graph-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  flex-shrink: 0;
}
.toolbar-left { display: flex; align-items: center; gap: 16px; }
.toolbar-title {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.22em;
  color: var(--accent);
  text-shadow: var(--glow-text);
}
.toolbar-stats { font-size: 10px; color: var(--text-tertiary); letter-spacing: 0.08em; }

.btn-load {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: 1px solid var(--accent-ring);
  border-radius: 4px;
  background: var(--accent-bg);
  color: var(--accent);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.15em;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-load:hover { background: rgba(0,212,255,0.16); border-color: var(--accent); }
.btn-load.loading { opacity: 0.6; cursor: wait; }
.btn-icon { font-size: 14px; }

/* Stage */
.graph-stage {
  flex: 1;
  position: relative;
  overflow: hidden;
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-void);
}
.graph-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

/* Tooltip */
.node-tooltip {
  position: fixed;
  max-width: 320px;
  padding: 10px 14px;
  z-index: 100;
  pointer-events: none;
}
.tip-badge {
  display: inline-block;
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.18em;
  padding: 2px 6px;
  border-radius: 2px;
  margin-bottom: 6px;
}
.tip-badge.observation { background: rgba(0,212,255,0.15); color: var(--accent); }
.tip-badge.experience { background: rgba(124,58,237,0.15); color: var(--quantum-glow); }
.tip-text { font-size: 11px; color: var(--text-primary); line-height: 1.5; margin: 0; }
.tip-meta { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.tip-entity { font-size: 9px; color: var(--text-tertiary); background: var(--bg-elevated); padding: 1px 6px; border-radius: 2px; }

/* Detail panel */
.detail-panel {
  position: absolute;
  right: 16px;
  top: 16px;
  width: 360px;
  max-height: calc(100% - 90px);
  overflow-y: auto;
  padding: 18px 20px;
  z-index: 50;
}
.panel-close {
  position: absolute;
  right: 12px;
  top: 12px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 14px;
  cursor: pointer;
  padding: 2px 6px;
}
.panel-close:hover { color: var(--text-primary); }
.panel-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.panel-badge {
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.18em;
  padding: 2px 8px;
  border-radius: 2px;
}
.panel-badge.observation { background: rgba(0,212,255,0.15); color: var(--accent); }
.panel-badge.experience { background: rgba(124,58,237,0.15); color: var(--quantum-glow); }
.panel-id { font-size: 10px; color: var(--text-disabled); font-family: monospace; }
.panel-text { font-size: 12px; color: var(--text-primary); line-height: 1.6; margin: 0 0 14px; }
.panel-section { margin-bottom: 12px; }
.panel-section h4 {
  font-size: 9px; font-weight: 700; letter-spacing: 0.18em;
  color: var(--text-tertiary); margin: 0 0 6px;
}
.chip-group { display: flex; flex-wrap: wrap; gap: 4px; }
.chip {
  font-size: 10px; padding: 2px 8px; border-radius: 3px;
  background: var(--bg-elevated); color: var(--accent);
  border: 1px solid rgba(0,212,255,0.15);
}
.chip.tag-chip { color: var(--quantum-glow); border-color: rgba(124,58,237,0.2); }
.panel-meta { border-top: 1px solid var(--border-subtle); padding-top: 10px; }
.meta-row { display: flex; justify-content: space-between; font-size: 10px; margin-bottom: 4px; }
.meta-row span { color: var(--text-tertiary); }
.meta-row strong { color: var(--text-secondary); }

/* Legend */
.legend {
  position: absolute;
  left: 16px;
  bottom: 16px;
  display: flex;
  gap: 16px;
  padding: 8px 14px;
  z-index: 10;
}
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 9px; color: var(--text-tertiary); }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; }
.legend-dot.obs { background: var(--accent); box-shadow: 0 0 8px rgba(0,212,255,0.4); }
.legend-dot.exp { background: var(--quantum); box-shadow: 0 0 8px rgba(124,58,237,0.4); }
.legend-line { width: 14px; height: 1px; }
.legend-line.sem { background: rgba(0,212,255,0.5); border-top: 1px dashed rgba(0,212,255,0.5); height: 0; }
.legend-line.tmp { background: var(--text-tertiary); opacity: 0.3; }

/* Transitions */
.panel-slide-enter-active { transition: all 0.25s ease; }
.panel-slide-leave-active { transition: all 0.15s ease; }
.panel-slide-enter-from { opacity: 0; transform: translateX(20px); }
.panel-slide-leave-to { opacity: 0; transform: translateX(20px); }
</style>
