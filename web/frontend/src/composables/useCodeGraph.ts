import { computed, onMounted, onUnmounted, ref } from "vue";
import * as THREE from "three";
import { api } from "../api";
import { applyNodeRiskStyles, buildCodeGraph } from "./codegraph/graphBuilder";
import { graphNodePreview, pickGraphNode, resetNodeScales } from "./codegraph/interaction";
import {
  CodeGraphSceneObjects,
  createCodeGraphScene,
  disposeCodeGraphScene,
  resizeCodeGraphScene,
} from "./codegraph/scene";
import {
  highlightGraphEdges,
  pulseSelectedEdges,
  syncNodeMeshes,
  tickForceLayout,
  updateEdgePositions,
} from "./codegraph/simulation";
import type {
  CodeGraphLevel,
  CodeGraphStatus,
  CodeGraphTranslate,
  EdgeMeta,
  GraphData,
  GraphNode,
  NodeRisk,
  SimLink,
  SimNode,
} from "./codegraph/types";

export type { CodeGraphTranslate } from "./codegraph/types";

type EdgeKind = "imports" | "calls" | "instantiates" | "references" | "extends";
const EDGE_KINDS: EdgeKind[] = ["imports", "calls", "instantiates", "references", "extends"];

export function useCodeGraph(t: CodeGraphTranslate) {
  const threeRef = ref<HTMLElement | null>(null);
  const isLoading = ref(false);
  const isSyncing = ref(false);
  const graphLoaded = ref(false);
  const graphVersion = ref(0);
  const level = ref<CodeGraphLevel>("module");
  const root = ref("");
  const status = ref<CodeGraphStatus | null>(null);
  const stats = ref<CodeGraphStatus | null>(null);
  const hoveredNode = ref<GraphNode | null>(null);
  const selectedNode = ref<GraphNode | null>(null);
  const tooltipStyle = ref({ left: "0px", top: "0px" });
  const loadError = ref("");
  const searchQuery = ref("");
  const searchResults = ref<GraphNode[]>([]);
  const selectedEdges = ref<EdgeKind[]>([...EDGE_KINDS]);
  const breadcrumb = computed(() => [
    { label: t("codegraph.modules"), level: "module" as CodeGraphLevel, root: "" },
    ...(root.value ? [{ label: root.value, level: level.value, root: root.value }] : []),
  ]);

  let three: CodeGraphSceneObjects | null = null;
  let nodeMeshes: Map<string, THREE.Mesh> = new Map();
  let allEdges: THREE.LineSegments | null = null;
  let edgeMeta: EdgeMeta[] = [];
  let simNodes: SimNode[] = [];
  let simLinks: SimLink[] = [];
  let animFrame = 0;
  let idleFrame = 0;
  let converged = false;
  let stillFrames = 0;

  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();

  function lineRange(node: GraphNode | null): string {
    if (!node?.start_line) return "—";
    return node.end_line && node.end_line !== node.start_line ? `${node.start_line}-${node.end_line}` : `${node.start_line}`;
  }

  function buildGraph(data: GraphData) {
    if (!three) return;
    const built = buildCodeGraph(data, three.scene, three.sphereGeo, nodeMeshes, allEdges);
    nodeMeshes = built.nodeMeshes;
    allEdges = built.allEdges;
    edgeMeta = built.edgeMeta;
    simNodes = built.simNodes;
    simLinks = built.simLinks;
  }

  function drawGraphFrame() {
    if (!three) return;
    syncNodeMeshes(simNodes, nodeMeshes);
    updateEdgePositions(allEdges, edgeMeta, simNodes);
    pulseSelectedEdges(allEdges, edgeMeta, selectedNode.value?.id || null, performance.now());
    three.renderer.render(three.scene, three.camera);
  }

  function tick() {
    if (!three) return;
    const maxVelocity = tickForceLayout(simNodes, simLinks);
    if (maxVelocity < 0.08) {
      stillFrames++;
      if (stillFrames > 60) {
        converged = true;
        drawGraphFrame();
        return;
      }
    } else {
      stillFrames = 0;
    }

    drawGraphFrame();
    animFrame = requestAnimationFrame(tick);
  }

  function restartSimulation() {
    converged = false;
    stillFrames = 0;
    cancelAnimationFrame(animFrame);
    animFrame = requestAnimationFrame(tick);
  }

  function deselectNode() {
    selectedNode.value = null;
    highlightGraphEdges(allEdges, edgeMeta, null);
  }

  function renderLoop() {
    if (!three) return;
    idleFrame = requestAnimationFrame(renderLoop);
    three.controls.update();
    if (converged) drawGraphFrame();
  }

  async function loadStatus() {
    status.value = await api.codeGraphStatus();
  }

  async function loadGraph(nextLevel: CodeGraphLevel = level.value, nextRoot = root.value) {
    isLoading.value = true;
    loadError.value = "";
    try {
      await loadStatus();
      const data = await api.codeGraphGraph({
        level: nextLevel,
        root: nextRoot,
        edge_kinds: selectedEdges.value.join(","),
      }) as GraphData;
      level.value = data.level;
      root.value = nextRoot;
      stats.value = data.stats || null;
      deselectNode();
      buildGraph(data);
      graphLoaded.value = true;
      graphVersion.value += 1;
      restartSimulation();
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : t("codegraph.loadError");
      console.error("Failed to load codegraph:", error);
    } finally {
      isLoading.value = false;
    }
  }

  async function loadNeighborhood(nodeId: string) {
    isLoading.value = true;
    loadError.value = "";
    try {
      const data = await api.codeGraphNeighborhood(nodeId) as GraphData;
      level.value = "neighborhood";
      root.value = selectedNode.value?.label || nodeId;
      stats.value = data.stats || null;
      buildGraph(data);
      graphLoaded.value = true;
      graphVersion.value += 1;
      restartSimulation();
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : t("codegraph.loadError");
    } finally {
      isLoading.value = false;
    }
  }

  async function runSearch() {
    const query = searchQuery.value.trim();
    if (!query) {
      searchResults.value = [];
      return;
    }
    searchResults.value = (await api.codeGraphSearch(query)).items as GraphNode[];
  }

  async function openSearchResult(node: GraphNode) {
    searchResults.value = [];
    searchQuery.value = node.label;
    if (node.kind === "file") await loadGraph("symbol", node.path);
    else await loadNeighborhood(node.id);
  }

  async function syncIndex(mode: "sync" | "rebuild") {
    isSyncing.value = true;
    loadError.value = "";
    try {
      await api.codeGraphSync(mode);
      await loadGraph("module", "");
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : t("codegraph.syncError");
    } finally {
      isSyncing.value = false;
    }
  }

  function toggleEdgeKind(kind: EdgeKind) {
    selectedEdges.value = selectedEdges.value.includes(kind)
      ? selectedEdges.value.filter(item => item !== kind)
      : [...selectedEdges.value, kind];
    if (!selectedEdges.value.length) selectedEdges.value = [kind];
    void loadGraph(level.value, root.value);
  }

  async function activateNode(node: SimNode) {
    selectedNode.value = graphNodePreview(node);
    highlightGraphEdges(allEdges, edgeMeta, node.id);
    if (node.kind === "module") await loadGraph("file", node.path);
    else if (node.kind === "file") await loadGraph("symbol", node.path);
    else if (level.value === "symbol") await loadNeighborhood(node.id);
    else if (converged) restartSimulation();
  }

  function onPointerDown(event: PointerEvent) {
    if (!three || !threeRef.value) return;
    const picked = pickGraphNode(event, threeRef.value, three.camera, nodeMeshes, simNodes, raycaster, mouse);
    if (!picked) {
      deselectNode();
      return;
    }
    void activateNode(picked.node);
  }

  function onPointerMove(event: PointerEvent) {
    if (!three || !threeRef.value) return;
    const picked = pickGraphNode(event, threeRef.value, three.camera, nodeMeshes, simNodes, raycaster, mouse);
    if (!picked) {
      hoveredNode.value = null;
      threeRef.value.style.cursor = "grab";
      resetNodeScales(nodeMeshes, simNodes);
      return;
    }

    const baseScale = picked.object.userData.scale as number;
    picked.object.scale.setScalar(baseScale * 1.3);
    threeRef.value.style.cursor = "pointer";
    hoveredNode.value = graphNodePreview(picked.node);
    tooltipStyle.value = {
      left: `${event.clientX + 14}px`,
      top: `${event.clientY - 10}px`,
    };
  }

  function resize() {
    if (three && threeRef.value) resizeCodeGraphScene(three, threeRef.value);
  }

  function applyDiagnosticsNodeRisks(risks: Record<string, NodeRisk>) {
    applyNodeRiskStyles(nodeMeshes, simNodes, risks);
    if (converged) drawGraphFrame();
  }

  onMounted(() => {
    if (!threeRef.value) return;
    three = createCodeGraphScene(threeRef.value);
    window.addEventListener("resize", resize);
    threeRef.value.addEventListener("pointerdown", onPointerDown);
    threeRef.value.addEventListener("pointermove", onPointerMove);
    renderLoop();
    void loadGraph("module", "");
  });

  onUnmounted(() => {
    cancelAnimationFrame(animFrame);
    cancelAnimationFrame(idleFrame);
    window.removeEventListener("resize", resize);
    threeRef.value?.removeEventListener("pointerdown", onPointerDown);
    threeRef.value?.removeEventListener("pointermove", onPointerMove);
    disposeCodeGraphScene(three);
  });

  return {
    threeRef,
    isLoading,
    isSyncing,
    graphLoaded,
    graphVersion,
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
    edgeKinds: EDGE_KINDS,
    breadcrumb,
    loadGraph,
    runSearch,
    openSearchResult,
    syncIndex,
    toggleEdgeKind,
    applyDiagnosticsNodeRisks,
    deselectNode,
    lineRange,
  };
}
