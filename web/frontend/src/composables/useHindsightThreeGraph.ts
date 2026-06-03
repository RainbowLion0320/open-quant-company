import { onMounted, onUnmounted, ref } from "vue";
import * as THREE from "three";
import { api } from "../api";
import { buildHindsightGraph } from "./hindsight/graphBuilder";
import {
  graphNodePreview,
  pickGraphNode,
  resetNodeScales,
} from "./hindsight/interaction";
import {
  createHindsightScene,
  disposeHindsightScene,
  HindsightSceneObjects,
  resizeHindsightScene,
} from "./hindsight/scene";
import {
  highlightGraphEdges,
  syncNodeMeshes,
  tickForceLayout,
  updateEdgePositions,
} from "./hindsight/simulation";
import type {
  EdgeMeta,
  GraphData,
  GraphNode,
  HindsightTranslate,
  SimLink,
  SimNode,
} from "./hindsight/types";

export type { HindsightTranslate } from "./hindsight/types";

export function useHindsightThreeGraph(t: HindsightTranslate) {
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

  let three: HindsightSceneObjects | null = null;
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

  function fmtDate(date: string): string {
    if (!date) return "—";
    return date.slice(0, 10);
  }

  function buildGraph(data: GraphData) {
    if (!three) return;
    const built = buildHindsightGraph(data, three.scene, three.sphereGeo, nodeMeshes, allEdges);
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
    if (converged) three.renderer.render(three.scene, three.camera);
  }

  function onPointerDown(event: PointerEvent) {
    if (!three || !threeRef.value) return;
    const picked = pickGraphNode(event, threeRef.value, three.camera, nodeMeshes, simNodes, raycaster, mouse);
    if (!picked) {
      deselectNode();
      return;
    }

    selectedNode.value = graphNodePreview(picked.node);
    highlightGraphEdges(allEdges, edgeMeta, picked.node.id);
    if (converged) restartSimulation();
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

  async function loadGraph() {
    isLoading.value = true;
    loadError.value = "";
    try {
      const data = await api.hindsightGraph() as GraphData;
      stats.value = data.stats || null;
      linkCount.value = data.links?.length || 0;
      buildGraph(data);
      graphLoaded.value = true;
      restartSimulation();
    } catch (error) {
      loadError.value = error instanceof Error ? error.message : t("hindsight.loadError");
      console.error("Failed to load graph:", error);
    } finally {
      isLoading.value = false;
    }
  }

  function resize() {
    if (three && threeRef.value) resizeHindsightScene(three, threeRef.value);
  }

  onMounted(() => {
    if (!threeRef.value) return;
    three = createHindsightScene(threeRef.value);
    window.addEventListener("resize", resize);
    threeRef.value.addEventListener("pointerdown", onPointerDown);
    threeRef.value.addEventListener("pointermove", onPointerMove);
    renderLoop();
  });

  onUnmounted(() => {
    cancelAnimationFrame(animFrame);
    cancelAnimationFrame(idleFrame);
    window.removeEventListener("resize", resize);
    threeRef.value?.removeEventListener("pointerdown", onPointerDown);
    threeRef.value?.removeEventListener("pointermove", onPointerMove);
    disposeHindsightScene(three);
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
