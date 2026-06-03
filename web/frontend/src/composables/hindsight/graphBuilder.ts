import * as THREE from "three";
import {
  EdgeMeta,
  GraphData,
  GraphLink,
  GraphNode,
  HINDSIGHT_COLORS,
  SimLink,
  SimNode,
} from "./types";

export interface BuiltHindsightGraph {
  nodeMeshes: Map<string, THREE.Mesh>;
  allEdges: THREE.LineSegments | null;
  edgeMeta: EdgeMeta[];
  simNodes: SimNode[];
  simLinks: SimLink[];
}

export function buildHindsightGraph(
  data: GraphData,
  scene: THREE.Scene,
  sphereGeo: THREE.SphereGeometry,
  previousNodeMeshes: Map<string, THREE.Mesh>,
  previousEdges: THREE.LineSegments | null,
): BuiltHindsightGraph {
  clearPreviousGraph(scene, previousNodeMeshes, previousEdges);

  const degree = calculateDegrees(data.nodes, data.links);
  const simNodes = createSimNodes(data.nodes, degree);
  const nodeMeshes = createNodeMeshes(scene, sphereGeo, simNodes);
  const { allEdges, edgeMeta, simLinks } = createEdges(scene, data, simNodes);
  return { nodeMeshes, allEdges, edgeMeta, simNodes, simLinks };
}

function clearPreviousGraph(
  scene: THREE.Scene,
  previousNodeMeshes: Map<string, THREE.Mesh>,
  previousEdges: THREE.LineSegments | null,
) {
  for (const mesh of previousNodeMeshes.values()) {
    scene.remove(mesh);
    disposeMeshMaterial(mesh);
  }
  previousNodeMeshes.clear();
  if (previousEdges) {
    scene.remove(previousEdges);
    previousEdges.geometry.dispose();
    disposeLineMaterial(previousEdges.material);
  }
}

function calculateDegrees(nodes: GraphNode[], links: GraphLink[]): Map<string, number> {
  const degree = new Map<string, number>();
  for (const node of nodes) degree.set(node.id, 0);
  for (const link of links) {
    const srcId = nodeFromLink(link.source, nodes).id;
    const tgtId = nodeFromLink(link.target, nodes).id;
    degree.set(srcId, (degree.get(srcId) || 0) + 1);
    degree.set(tgtId, (tgtId === srcId ? 0 : 1) + (degree.get(tgtId) || 0));
  }
  return degree;
}

function createSimNodes(nodes: GraphNode[], degree: Map<string, number>): SimNode[] {
  const radius = Math.min(nodes.length * 3, 180);
  return nodes.map((node) => {
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = radius * Math.cbrt(Math.random()) * 0.6;
    return {
      ...node,
      x: r * Math.sin(phi) * Math.cos(theta),
      y: r * Math.sin(phi) * Math.sin(theta),
      z: r * Math.cos(phi),
      vx: 0,
      vy: 0,
      vz: 0,
      degree: degree.get(node.id) || 0,
    };
  });
}

function createNodeMeshes(
  scene: THREE.Scene,
  sphereGeo: THREE.SphereGeometry,
  simNodes: SimNode[],
): Map<string, THREE.Mesh> {
  const nodeMeshes = new Map<string, THREE.Mesh>();
  const maxDegree = maxNodeDegree(simNodes);
  for (const node of simNodes) {
    const degRatio = node.degree / maxDegree;
    const scale = nodeScale(node, maxDegree);
    const color = nodeColor(node);
    const material = new THREE.MeshStandardMaterial({
      color,
      emissive: color,
      emissiveIntensity: 0.3 + degRatio * 0.4,
      roughness: 0.5,
      metalness: 0.1,
    });
    const mesh = new THREE.Mesh(sphereGeo, material);
    mesh.position.set(node.x, node.y, node.z);
    mesh.scale.setScalar(scale);
    mesh.userData = { nodeId: node.id, type: node.type, scale, degRatio };
    scene.add(mesh);
    nodeMeshes.set(node.id, mesh);
  }
  return nodeMeshes;
}

function createEdges(scene: THREE.Scene, data: GraphData, simNodes: SimNode[]) {
  const allPositions: number[] = [];
  const allColors: number[] = [];
  const edgeMeta: EdgeMeta[] = [];
  const simLinks: SimLink[] = [];
  const typeBaseSpec: Record<string, { color: number; opacity: number }> = {
    semantic: { color: HINDSIGHT_COLORS.semantic, opacity: 0.35 },
    temporal: { color: HINDSIGHT_COLORS.temporal, opacity: 0.15 },
    consolidation: { color: HINDSIGHT_COLORS.consolidation, opacity: 0.20 },
    tag: { color: HINDSIGHT_COLORS.tag, opacity: 0.12 },
  };

  for (const link of data.links) {
    const srcNode = nodeFromLink(link.source, data.nodes);
    const tgtNode = nodeFromLink(link.target, data.nodes);
    const src = simNodes.find(item => item.id === srcNode.id);
    const tgt = simNodes.find(item => item.id === tgtNode.id);
    if (!src || !tgt) continue;

    simLinks.push({ source: src, target: tgt, type: link.type });
    const edgeType = link.type || "temporal";
    const spec = typeBaseSpec[edgeType] || typeBaseSpec.temporal;
    const color = new THREE.Color(spec.color);
    allPositions.push(src.x, src.y, src.z, tgt.x, tgt.y, tgt.z);
    allColors.push(color.r, color.g, color.b, color.r, color.g, color.b);
    edgeMeta.push({
      srcId: src.id,
      tgtId: tgt.id,
      type: edgeType,
      baseOpacity: spec.opacity,
      baseColor: color.clone(),
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
  const allEdges = new THREE.LineSegments(edgeGeo, edgeMat);
  scene.add(allEdges);
  return { allEdges, edgeMeta, simLinks };
}

export function nodeScale(node: SimNode, maxDegree: number): number {
  return 1.8 + (node.degree / Math.max(1, maxDegree)) * 4.5;
}

export function maxNodeDegree(simNodes: SimNode[]): number {
  return Math.max(1, ...simNodes.map(node => node.degree));
}

function nodeColor(node: SimNode): number {
  if (node.type === "experience") return HINDSIGHT_COLORS.exp;
  if (node.type === "world") return HINDSIGHT_COLORS.world;
  return HINDSIGHT_COLORS.obs;
}

function nodeFromLink(linkNode: number | GraphNode, nodes: GraphNode[]): GraphNode {
  return typeof linkNode === "number" ? nodes[linkNode] : linkNode;
}

function disposeMeshMaterial(mesh: THREE.Mesh) {
  const material = mesh.material;
  if (Array.isArray(material)) material.forEach(item => item.dispose());
  else material.dispose();
}

function disposeLineMaterial(material: THREE.Material | THREE.Material[]) {
  if (Array.isArray(material)) material.forEach(item => item.dispose());
  else material.dispose();
}
