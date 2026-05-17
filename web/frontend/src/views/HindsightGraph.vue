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

    <!-- 3D 容器 -->
    <div class="graph-stage" ref="stageRef">
      <div ref="threeRef" class="three-container"></div>

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
          <button class="panel-close" @click="deselectNode">✕</button>
          <div class="panel-header">
            <span class="panel-badge" :class="selectedNode.type">
              {{ selectedNode.type }}
            </span>
            <span class="panel-id">#{{ selectedNode.id?.slice(0, 8) }}</span>
            <span class="panel-degree">deg: {{ selectedNode.degree || 0 }}</span>
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
        <div class="legend-item"><span class="legend-line tag-l"></span> Tag</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from "vue";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls";

// ── Types ──
interface GraphNode {
  id: string; index: number; label: string; fullText: string;
  type: "observation" | "experience"; entities: string[]; tags: string[];
  date: string; documentId: string | null; chunkId: string | null;
  consolidatedAt: string | null; proofCount: number;
  x?: number; y?: number; z?: number; vx?: number; vy?: number; vz?: number;
  degree?: number;
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
  x: number; y: number; z: number;
  vx: number; vy: number; vz: number;
  fx?: number | null; fy?: number | null; fz?: number | null;
  degree: number;
}

// ── Vue state ──
const threeRef = ref<HTMLElement | null>(null);
const stageRef = ref<HTMLElement | null>(null);
const isLoading = ref(false);
const stats = ref<GraphData["stats"] | null>(null);
const hoveredNode = ref<GraphNode | null>(null);
const selectedNode = ref<GraphNode | null>(null);
const tooltipStyle = ref({ left: "0px", top: "0px" });
const linkCount = ref(0);

// ── Three.js objects ──
let scene: THREE.Scene;
let camera: THREE.PerspectiveCamera;
let renderer: THREE.WebGLRenderer;
let controls: OrbitControls;
let nodeMeshes: Map<string, THREE.Mesh> = new Map();
let edgeSegments: Map<string, THREE.LineSegments> = new Map();
let selectedNodeId: string | null = null;
let sphereGeo: THREE.SphereGeometry;
let starfield: THREE.Points;

// ── Simulation state ──
let simNodes: SimNode[] = [];
let simLinks: { source: SimNode; target: SimNode; type: string }[] = [];
let animFrame = 0;
let converged = false;
let stillFrames = 0;
let graphDataRef: GraphData | null = null;

// ── Colors ──
const COLORS = {
  obs: 0x00d4ff,
  exp: 0x7c3aed,
  semantic: 0x00d4ff,
  temporal: 0x64748b,
  consolidation: 0x00ffc8,
  tag: 0x7c3aed,
};

function fmtDate(d: string): string {
  if (!d) return "—";
  return d.slice(0, 10);
}

// ── Three.js Init ──
function initThree() {
  const container = threeRef.value!;
  const w = container.clientWidth;
  const h = container.clientHeight;

  scene = new THREE.Scene();
  scene.background = new THREE.Color("#02060d");

  camera = new THREE.PerspectiveCamera(55, w / h, 0.5, 2000);
  camera.position.set(0, 0, 160);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(w, h);
  container.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.15;
  controls.minDistance = 30;
  controls.maxDistance = 600;
  controls.target.set(0, 0, 0);

  // Lights
  scene.add(new THREE.AmbientLight(0x334466, 1.2));
  const pointLight = new THREE.PointLight(0x00d4ff, 0.6, 500);
  pointLight.position.set(0, 0, 200);
  scene.add(pointLight);

  // Shared sphere geometry
  sphereGeo = new THREE.SphereGeometry(1, 24, 16);

  // Starfield particles
  const starCount = 600;
  const starsGeo = new THREE.BufferGeometry();
  const starPositions = new Float32Array(starCount * 3);
  for (let i = 0; i < starCount; i++) {
    starPositions[i * 3] = (Math.random() - 0.5) * 800;
    starPositions[i * 3 + 1] = (Math.random() - 0.5) * 800;
    starPositions[i * 3 + 2] = (Math.random() - 0.5) * 800;
  }
  starsGeo.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
  const starsMat = new THREE.PointsMaterial({
    color: 0x334466,
    size: 0.6,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  starfield = new THREE.Points(starsGeo, starsMat);
  scene.add(starfield);
}

// ── Graph building ──
function buildGraph(data: GraphData) {
  // Clear old meshes
  for (const mesh of nodeMeshes.values()) scene.remove(mesh);
  for (const seg of edgeSegments.values()) scene.remove(seg);
  nodeMeshes.clear();
  edgeSegments.clear();
  simNodes = [];
  simLinks = [];

  const nodes = data.nodes;
  const links = data.links;

  // Calculate degree
  const degree = new Map<string, number>();
  for (const n of nodes) degree.set(n.id, 0);
  for (const l of links) {
    const srcId = typeof l.source === "number" ? nodes[l.source].id : (l.source as GraphNode).id;
    const tgtId = typeof l.target === "number" ? nodes[l.target].id : (l.target as GraphNode).id;
    degree.set(srcId, (degree.get(srcId) || 0) + 1);
    degree.set(tgtId, (tgtId === srcId ? 0 : 1) + (degree.get(tgtId) || 0));
  }

  // Create sim nodes (3D)
  const radius = Math.min(nodes.length * 3, 180);
  simNodes = nodes.map((n) => {
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = radius * Math.cbrt(Math.random()) * 0.6;
    return {
      ...n,
      x: r * Math.sin(phi) * Math.cos(theta),
      y: r * Math.sin(phi) * Math.sin(theta),
      z: r * Math.cos(phi),
      vx: 0, vy: 0, vz: 0,
      degree: degree.get(n.id) || 0,
    };
  });

  // Create 3D meshes
  const maxDeg = Math.max(1, ...simNodes.map((n) => n.degree));
  for (const n of simNodes) {
    const degRatio = n.degree / maxDeg;
    const scale = 1.8 + degRatio * 4.5; // degree → size: 1.8 ~ 6.3
    const color = n.type === "experience" ? COLORS.exp : COLORS.obs;
    const mat = new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: 0.3 + degRatio * 0.4,
      roughness: 0.5,
      metalness: 0.1,
    });
    const mesh = new THREE.Mesh(sphereGeo, mat);
    mesh.position.set(n.x, n.y, n.z);
    mesh.scale.setScalar(scale);
    mesh.userData = { nodeId: n.id, type: n.type, scale, degRatio };
    scene.add(mesh);
    nodeMeshes.set(n.id, mesh);
  }

  // Create edge groups by type
  const edgeGroups: Record<string, { points: number[][]; ids: [string, string][] }> = {};
  for (const l of links) {
    const srcN = typeof l.source === "number" ? nodes[l.source] : (l.source as GraphNode);
    const tgtN = typeof l.target === "number" ? nodes[l.target] : (l.target as GraphNode);
    const src = simNodes.find((sn) => sn.id === srcN.id);
    const tgt = simNodes.find((sn) => sn.id === tgtN.id);
    if (!src || !tgt) continue;
    simLinks.push({ source: src, target: tgt, type: l.type });
    const type = l.type || "temporal";
    if (!edgeGroups[type]) edgeGroups[type] = { points: [], ids: [] };
    edgeGroups[type].points.push([src.x, src.y, src.z, tgt.x, tgt.y, tgt.z]);
    edgeGroups[type].ids.push([src.id, tgt.id]);
  }

  // Edge colors per type
  const typeColors: Record<string, number> = {
    semantic: COLORS.semantic,
    temporal: COLORS.temporal,
    consolidation: COLORS.consolidation,
    tag: COLORS.tag,
  };

  for (const [etype, group] of Object.entries(edgeGroups)) {
    const positions: number[] = [];
    for (const p of group.points) positions.push(...p);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    const color = typeColors[etype] || COLORS.temporal;
    const mat = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: etype === "semantic" ? 0.5 : 0.2,
      depthWrite: false,
    });
    const seg = new THREE.LineSegments(geo, mat);
    seg.userData = { edgeType: etype, edgeIds: group.ids };
    scene.add(seg);
    edgeSegments.set(etype, seg);
  }

  graphDataRef = data;
}

// ── Force simulation (3D) ──
function tick() {
  const centering = 0.003;
  const damping = 0.85;
  const repulsion = 400;
  const springLen = 45;
  const springK = 0.003;

  for (const n of simNodes) {
    if (n.fx != null) continue;
    for (const m of simNodes) {
      if (n === m) continue;
      let dx = n.x - m.x;
      let dy = n.y - m.y;
      let dz = n.z - m.z;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy + dz * dz), 1);
      const force = repulsion / (dist * dist);
      n.vx += (dx / dist) * force;
      n.vy += (dy / dist) * force;
      n.vz += (dz / dist) * force;
    }
    n.vx -= n.x * centering;
    n.vy -= n.y * centering;
    n.vz -= n.z * centering;
    n.vx *= damping;
    n.vy *= damping;
    n.vz *= damping;
    n.x += n.vx;
    n.y += n.vy;
    n.z += n.vz;
  }

  for (const l of simLinks) {
    const s = l.source; const t = l.target;
    let dx = t.x - s.x, dy = t.y - s.y, dz = t.z - s.z;
    const dist = Math.max(Math.sqrt(dx * dx + dy * dy + dz * dz), 1);
    const disp = (dist - springLen) * springK;
    const fx = (dx / dist) * disp, fy = (dy / dist) * disp, fz = (dz / dist) * disp;
    if (s.fx == null) { s.vx += fx; s.vy += fy; s.vz += fz; }
    if (t.fx == null) { t.vx -= fx; t.vy -= fy; t.vz -= fz; }
  }

  // Convergence
  let maxV = 0;
  for (const n of simNodes) {
    if (n.fx != null) continue;
    const speed = Math.sqrt(n.vx * n.vx + n.vy * n.vy + n.vz * n.vz);
    if (speed > maxV) maxV = speed;
  }
  if (maxV < 0.08) {
    stillFrames++;
    if (stillFrames > 60) {
      converged = true;
      syncPositions();
      updateEdges();
      renderer.render(scene, camera);
      return;
    }
  } else {
    stillFrames = 0;
  }

  syncPositions();
  updateEdges();
  renderer.render(scene, camera);
  animFrame = requestAnimationFrame(tick);
}

function syncPositions() {
  for (const n of simNodes) {
    const mesh = nodeMeshes.get(n.id);
    if (mesh) mesh.position.set(n.x, n.y, n.z);
  }
}

function updateEdges() {
  for (const [etype, seg] of edgeSegments) {
    const group = (seg.userData as any).edgeIds as [string, string][];
    const positions = seg.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < group.length; i++) {
      const [srcId, tgtId] = group[i];
      const src = simNodes.find((sn) => sn.id === srcId);
      const tgt = simNodes.find((sn) => sn.id === tgtId);
      const off = i * 6;
      if (src && tgt) {
        positions[off] = src.x; positions[off + 1] = src.y; positions[off + 2] = src.z;
        positions[off + 3] = tgt.x; positions[off + 4] = tgt.y; positions[off + 5] = tgt.z;
      }
    }
    seg.geometry.attributes.position.needsUpdate = true;
  }
}

// ── Selection highlighting ──
function highlightEdges(nodeId: string | null) {
  selectedNodeId = nodeId;
  if (!nodeId || !graphDataRef) {
    // Reset all
    for (const [, seg] of edgeSegments) {
      const mat = seg.material as THREE.LineBasicMaterial;
      mat.opacity = seg.userData.edgeType === "semantic" ? 0.5 : 0.2;
      mat.color.set(COLORS[seg.userData.edgeType as keyof typeof COLORS] || COLORS.temporal);
    }
    return;
  }

  // Find connected node IDs
  const connected = new Set<string>();
  for (const [, seg] of edgeSegments) {
    const ids = (seg.userData as any).edgeIds as [string, string][];
    for (const [s, t] of ids) {
      if (s === nodeId) connected.add(t);
      if (t === nodeId) connected.add(s);
    }
  }

  for (const [, seg] of edgeSegments) {
    const ids = (seg.userData as any).edgeIds as [string, string][];
    const mat = seg.material as THREE.LineBasicMaterial;
    let isConnected = false;
    for (const [s, t] of ids) {
      if (s === nodeId || t === nodeId) { isConnected = true; break; }
    }
    if (isConnected) {
      mat.opacity = 0.9;
      mat.color.set(0xffffff);
    } else {
      mat.opacity = 0.05;
      mat.color.set(0x1a1a2e);
    }
  }
}

// ── Interaction ──
function deselectNode() {
  selectedNode.value = null;
  highlightEdges(null);
}

function onClick(event: THREE.Event) {
  // handled via raycaster in animate loop
}

// ── Animation loop (idle render + controls) ──
let idleFrame = 0;
function renderLoop() {
  idleFrame = requestAnimationFrame(renderLoop);
  controls.update();
  if (converged) renderer.render(scene, camera);
}

// ── Raycaster setup ──
const raycaster = new THREE.Raycaster();
const mouse = new THREE.Vector2();

function onPointerDown(event: PointerEvent) {
  const container = threeRef.value!;
  const rect = container.getBoundingClientRect();
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

  raycaster.setFromCamera(mouse, camera);
  const meshes = Array.from(nodeMeshes.values());
  const intersects = raycaster.intersectObjects(meshes);
  if (intersects.length > 0) {
    const nodeId = intersects[0].object.userData.nodeId as string;
    const sn = simNodes.find((n) => n.id === nodeId);
    if (sn) {
      selectedNode.value = { ...sn, fullText: sn.fullText || sn.label };
      highlightEdges(nodeId);
      // Restart sim briefly for visual feedback
      stillFrames = 0;
      if (converged) {
        converged = false;
        animFrame = requestAnimationFrame(tick);
      }
    }
  } else {
    // Clicked empty space
    deselectNode();
  }
}

function onPointerMove(event: PointerEvent) {
  const container = threeRef.value!;
  const rect = container.getBoundingClientRect();
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

  raycaster.setFromCamera(mouse, camera);
  const meshes = Array.from(nodeMeshes.values());
  const intersects = raycaster.intersectObjects(meshes);
  if (intersects.length > 0) {
    const obj = intersects[0].object;
    // Scale up hover
    const baseScale = obj.userData.scale as number;
    obj.scale.setScalar(baseScale * 1.3);
    container.style.cursor = "pointer";

    const nodeId = obj.userData.nodeId as string;
    const sn = simNodes.find((n) => n.id === nodeId);
    if (sn) {
      hoveredNode.value = {
        id: sn.id, index: sn.index, label: sn.label, fullText: sn.fullText,
        type: sn.type, entities: sn.entities, tags: sn.tags, date: sn.date,
        documentId: sn.documentId || null, chunkId: sn.chunkId || null,
        consolidatedAt: sn.consolidatedAt || null, proofCount: sn.proofCount,
        degree: sn.degree,
      };
      tooltipStyle.value = {
        left: `${event.clientX + 14}px`,
        top: `${event.clientY - 10}px`,
      };
    }
  } else {
    hoveredNode.value = null;
    container.style.cursor = "grab";
    // Reset all scales
    for (const [id, mesh] of nodeMeshes) {
      const sn = simNodes.find((n) => n.id === id);
      mesh.scale.setScalar(sn ? (1.8 + (sn.degree / Math.max(1, ...simNodes.map(n => n.degree))) * 4.5) : 1.8);
    }
  }
}

// ── Load ──
async function loadGraph() {
  isLoading.value = true;
  try {
    const res = await fetch("/api/hindsight/graph");
    const data: GraphData = await res.json();
    stats.value = data.stats || null;
    linkCount.value = data.links?.length || 0;
    buildGraph(data);

    converged = false;
    stillFrames = 0;
    cancelAnimationFrame(animFrame);
    animFrame = requestAnimationFrame(tick);
  } catch (e) {
    console.error("Failed to load graph:", e);
  } finally {
    isLoading.value = false;
  }
}

// ── Resize ──
function resize() {
  const container = threeRef.value!;
  const w = container.clientWidth;
  const h = container.clientHeight;
  if (renderer) {
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
}

// ── Lifecycle ──
onMounted(async () => {
  initThree();
  window.addEventListener("resize", resize);

  const container = threeRef.value!;
  container.addEventListener("pointerdown", onPointerDown);
  container.addEventListener("pointermove", onPointerMove);

  renderLoop();
  await loadGraph();
});

onUnmounted(() => {
  cancelAnimationFrame(animFrame);
  cancelAnimationFrame(idleFrame);
  window.removeEventListener("resize", resize);
  renderer?.dispose();
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
.toolbar-title {
  font-family: "JetBrains Mono", monospace;
  font-size: 14px;
  font-weight: 700;
  color: #00d4ff;
  letter-spacing: 2px;
  margin: 0;
}
.toolbar-stats {
  font-size: 11px;
  color: #64748b;
  margin-left: 16px;
  letter-spacing: 1px;
}
.btn-load {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: rgba(0, 212, 255, 0.08);
  border: 1px solid rgba(0, 212, 255, 0.2);
  color: #00d4ff;
  font-size: 11px;
  font-family: "JetBrains Mono", monospace;
  letter-spacing: 1px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-load:hover { background: rgba(0, 212, 255, 0.15); }
.btn-load.loading { opacity: 0.5; cursor: wait; }
.btn-icon { font-size: 14px; }

/* Stage */
.graph-stage {
  position: relative;
  flex: 1;
  overflow: hidden;
  border-radius: 8px;
  background: #02060d;
}
.three-container {
  width: 100%;
  height: 100%;
}
.three-container canvas {
  display: block;
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
  font-size: 9px;
  font-family: "JetBrains Mono", monospace;
  padding: 2px 8px;
  border-radius: 3px;
  margin-bottom: 6px;
  letter-spacing: 1px;
}
.tip-badge.observation { background: rgba(0, 212, 255, 0.2); color: #00d4ff; }
.tip-badge.experience { background: rgba(124, 58, 237, 0.2); color: #7c3aed; }
.tip-text {
  font-size: 12px;
  color: #e2e8f0;
  line-height: 1.5;
  margin: 0;
  max-height: 120px;
  overflow: hidden;
}
.tip-meta { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
.tip-entity {
  font-size: 10px;
  color: #64748b;
  background: rgba(148, 163, 184, 0.1);
  padding: 1px 6px;
  border-radius: 3px;
}

/* Detail panel */
.detail-panel {
  position: absolute;
  right: 16px;
  top: 16px;
  bottom: 16px;
  width: 340px;
  padding: 18px;
  overflow-y: auto;
  z-index: 50;
}
.panel-close {
  position: absolute;
  top: 12px;
  right: 14px;
  background: none;
  border: none;
  color: #64748b;
  font-size: 18px;
  cursor: pointer;
}
.panel-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.panel-badge {
  font-size: 10px;
  font-family: "JetBrains Mono", monospace;
  padding: 3px 8px;
  border-radius: 3px;
  letter-spacing: 1px;
}
.panel-badge.observation { background: rgba(0, 212, 255, 0.2); color: #00d4ff; }
.panel-badge.experience { background: rgba(124, 58, 237, 0.2); color: #7c3aed; }
.panel-id { font-size: 10px; color: #64748b; font-family: "JetBrains Mono", monospace; }
.panel-degree { font-size: 10px; color: #00d4ff; margin-left: auto; font-family: "JetBrains Mono", monospace; }
.panel-text {
  font-size: 13px;
  color: #cbd5e1;
  line-height: 1.7;
  margin: 0 0 14px 0;
}
.panel-section { margin-bottom: 12px; }
.panel-section h4 {
  font-size: 10px;
  color: #64748b;
  letter-spacing: 2px;
  margin: 0 0 6px 0;
}
.chip-group { display: flex; flex-wrap: wrap; gap: 4px; }
.chip {
  font-size: 11px;
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.08);
  padding: 3px 8px;
  border-radius: 3px;
}
.tag-chip { color: #7c3aed; background: rgba(124, 58, 237, 0.1); }
.panel-meta { border-top: 1px solid rgba(148, 163, 184, 0.1); padding-top: 10px; }
.meta-row { display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 4px; }
.meta-row strong { color: #e2e8f0; }

/* Legend */
.legend {
  position: absolute;
  bottom: 16px;
  left: 16px;
  padding: 10px 14px;
  display: flex;
  gap: 16px;
  font-size: 10px;
  color: #94a3b8;
  font-family: "JetBrains Mono", monospace;
}
.legend-item { display: flex; align-items: center; gap: 6px; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; }
.legend-dot.obs { background: #00d4ff; box-shadow: 0 0 8px rgba(0, 212, 255, 0.5); }
.legend-dot.exp { background: #7c3aed; box-shadow: 0 0 8px rgba(124, 58, 237, 0.5); }
.legend-line { width: 14px; height: 1px; }
.legend-line.sem { background: rgba(0, 212, 255, 0.5); }
.legend-line.tmp { background: rgba(100, 116, 139, 0.3); }
.legend-line.tag-l { background: rgba(124, 58, 237, 0.3); }

/* Panel slide transition */
.panel-slide-enter-active, .panel-slide-leave-active {
  transition: all 0.25s ease;
}
.panel-slide-enter-from, .panel-slide-leave-to {
  transform: translateX(40px);
  opacity: 0;
}

/* Glass card utility — keep consistent */
.glass-card {
  background: rgba(10, 20, 40, 0.85);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(0, 212, 255, 0.08);
  border-radius: 6px;
}
</style>
