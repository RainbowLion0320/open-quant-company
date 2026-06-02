import { ref, onMounted, onUnmounted } from "vue";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { api } from "../api";

export type HindsightTranslate = (key: string, params?: Record<string, any>) => string;

// ── Types ──
interface GraphNode {
  id: string; index: number; label: string; fullText: string;
  type: "observation" | "experience" | "world"; entities: string[]; tags: string[];
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

export function useHindsightThreeGraph(t: HindsightTranslate) {
// ── Vue state ──
const threeRef = ref<HTMLElement | null>(null);
const stageRef = ref<HTMLElement | null>(null);
const isLoading = ref(false);
const graphLoaded = ref(false);
const stats = ref<GraphData["stats"] | null>(null);
const hoveredNode = ref<GraphNode | null>(null);
const selectedNode = ref<GraphNode | null>(null);
const tooltipStyle = ref({ left: "0px", top: "0px" });
const linkCount = ref(0);
const loadError = ref("");

// ── Three.js objects ──
let scene: THREE.Scene;
let camera: THREE.PerspectiveCamera;
let renderer: THREE.WebGLRenderer;
let controls: OrbitControls;
let nodeMeshes: Map<string, THREE.Mesh> = new Map();
let edgeSegments: Map<string, THREE.LineSegments> = new Map();
let allEdges: THREE.LineSegments | null = null;
let edgeMeta: { srcId: string; tgtId: string; type: string; baseOpacity: number; baseColor: THREE.Color }[] = [];
let hasEdgeColors = false;
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
  world: 0xe8a840,
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
  nodeMeshes.clear();
  if (allEdges) { scene.remove(allEdges); allEdges = null; }
  edgeSegments.clear();
  edgeMeta = [];
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
    const color = n.type === "experience" ? COLORS.exp
                : n.type === "world" ? COLORS.world
                : COLORS.obs;
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

  // Build ALL edges into a single BufferGeometry with vertex colors
  // This gives per-edge color control (not per-type group)
  const allPositions: number[] = [];
  const allColors: number[] = [];
  edgeMeta = [];

  const typeBaseSpec: Record<string, { color: number; opacity: number }> = {
    semantic:     { color: COLORS.semantic,     opacity: 0.35 },
    temporal:     { color: COLORS.temporal,     opacity: 0.15 },
    consolidation:{ color: COLORS.consolidation,opacity: 0.20 },
    tag:          { color: COLORS.tag,          opacity: 0.12 },
  };

  for (const l of links) {
    const srcN = typeof l.source === "number" ? nodes[l.source] : (l.source as GraphNode);
    const tgtN = typeof l.target === "number" ? nodes[l.target] : (l.target as GraphNode);
    const src = simNodes.find((sn) => sn.id === srcN.id);
    const tgt = simNodes.find((sn) => sn.id === tgtN.id);
    if (!src || !tgt) continue;
    simLinks.push({ source: src, target: tgt, type: l.type });
    const etype = l.type || "temporal";
    const spec = typeBaseSpec[etype] || typeBaseSpec.temporal;
    const c = new THREE.Color(spec.color);

    allPositions.push(src.x, src.y, src.z, tgt.x, tgt.y, tgt.z);
    allColors.push(c.r, c.g, c.b,  c.r, c.g, c.b);
    edgeMeta.push({
      srcId: src.id, tgtId: tgt.id, type: etype,
      baseOpacity: spec.opacity, baseColor: c.clone(),
    });
  }

  const edgeGeo = new THREE.BufferGeometry();
  edgeGeo.setAttribute("position", new THREE.Float32BufferAttribute(allPositions, 3));
  edgeGeo.setAttribute("color", new THREE.Float32BufferAttribute(allColors, 3));
  const edgeMat = new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: 1.0,
    depthWrite: false,
  });
  allEdges = new THREE.LineSegments(edgeGeo, edgeMat);
  scene.add(allEdges);
  hasEdgeColors = true;

  // Also keep per-type groups for compatibility with updateEdges()
  edgeSegments.set("all", allEdges);
  (allEdges.userData as any) = { edgeIds: edgeMeta.map(m => [m.srcId, m.tgtId] as [string, string]) };

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
  if (!allEdges) return;
  const positions = allEdges.geometry.attributes.position.array as Float32Array;
  for (let i = 0; i < edgeMeta.length; i++) {
    const { srcId, tgtId } = edgeMeta[i];
    const src = simNodes.find((sn) => sn.id === srcId);
    const tgt = simNodes.find((sn) => sn.id === tgtId);
    const off = i * 6;
    if (src && tgt) {
      positions[off] = src.x; positions[off + 1] = src.y; positions[off + 2] = src.z;
      positions[off + 3] = tgt.x; positions[off + 4] = tgt.y; positions[off + 5] = tgt.z;
    }
  }
  allEdges.geometry.attributes.position.needsUpdate = true;
}

// ── Selection highlighting (per-edge via vertex colors) ──
function highlightEdges(nodeId: string | null) {
  selectedNodeId = nodeId;
  if (!allEdges) return;

  const colors = allEdges.geometry.attributes.color.array as Float32Array;
  const mat = allEdges.material as THREE.LineBasicMaterial;

  if (!nodeId) {
    // Reset all to base colors
    for (let i = 0; i < edgeMeta.length; i++) {
      const m = edgeMeta[i];
      const off = i * 6;
      colors[off] = m.baseColor.r;
      colors[off + 1] = m.baseColor.g;
      colors[off + 2] = m.baseColor.b;
      colors[off + 3] = m.baseColor.r;
      colors[off + 4] = m.baseColor.g;
      colors[off + 5] = m.baseColor.b;
    }
    mat.opacity = 1.0;
  } else {
    // Connected edges → white bright; others → dim near-black
    const dim = new THREE.Color(0x111122);
    const bright = new THREE.Color(0xffffff);
    for (let i = 0; i < edgeMeta.length; i++) {
      const m = edgeMeta[i];
      const connected = m.srcId === nodeId || m.tgtId === nodeId;
      const c = connected ? bright : dim;
      const off = i * 6;
      colors[off] = c.r;
      colors[off + 1] = c.g;
      colors[off + 2] = c.b;
      colors[off + 3] = c.r;
      colors[off + 4] = c.g;
      colors[off + 5] = c.b;
    }
    mat.opacity = 1.0;
  }
  allEdges.geometry.attributes.color.needsUpdate = true;
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
  loadError.value = "";
  try {
    const data = await api.hindsightGraph() as GraphData;
    stats.value = data.stats || null;
    linkCount.value = data.links?.length || 0;
    buildGraph(data);
    graphLoaded.value = true;

    converged = false;
    stillFrames = 0;
    cancelAnimationFrame(animFrame);
    animFrame = requestAnimationFrame(tick);
  } catch (e) {
    loadError.value = e instanceof Error ? e.message : t("hindsight.loadError");
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
});

onUnmounted(() => {
  cancelAnimationFrame(animFrame);
  cancelAnimationFrame(idleFrame);
  window.removeEventListener("resize", resize);
  renderer?.dispose();
});

  return {
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
  };
}
