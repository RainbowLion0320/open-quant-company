import * as THREE from "three";
import {
  CODEGRAPH_COLORS,
  EdgeMeta,
  GraphData,
  GraphLink,
  GraphNode,
  NodeRisk,
  SimLink,
  SimNode,
} from "./types";

export interface BuiltCodeGraph {
  nodeMeshes: Map<string, THREE.Mesh>;
  allEdges: THREE.LineSegments | null;
  edgeMeta: EdgeMeta[];
  simNodes: SimNode[];
  simLinks: SimLink[];
}

export function buildCodeGraph(
  data: GraphData,
  scene: THREE.Scene,
  sphereGeo: THREE.SphereGeometry,
  previousNodeMeshes: Map<string, THREE.Mesh>,
  previousEdges: THREE.LineSegments | null,
): BuiltCodeGraph {
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
  for (const node of nodes) degree.set(node.id, node.degree || 0);
  for (const link of links) {
    const srcId = nodeFromLink(link.source, nodes)?.id;
    const tgtId = nodeFromLink(link.target, nodes)?.id;
    if (!srcId || !tgtId) continue;
    degree.set(srcId, (degree.get(srcId) || 0) + Math.max(1, link.count || 1));
    degree.set(tgtId, (degree.get(tgtId) || 0) + Math.max(1, link.count || 1));
  }
  return degree;
}

function createSimNodes(nodes: GraphNode[], degree: Map<string, number>): SimNode[] {
  const radius = Math.min(Math.max(nodes.length * 4, 60), 220);
  return nodes.map((node, index) => {
    const theta = (index / Math.max(1, nodes.length)) * Math.PI * 2;
    const phi = Math.acos(2 * ((index * 37) % Math.max(2, nodes.length)) / Math.max(2, nodes.length) - 1);
    const r = radius * (0.35 + (index % 7) * 0.07);
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
      emissiveIntensity: 0.25 + degRatio * 0.45,
      roughness: 0.52,
      metalness: 0.12,
    });
    const mesh = new THREE.Mesh(sphereGeo, material);
    mesh.position.set(node.x, node.y, node.z);
    mesh.scale.setScalar(scale);
    mesh.userData = { nodeId: node.id, kind: node.kind, scale, degRatio };
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

  for (const link of data.links) {
    const srcNode = nodeFromLink(link.source, data.nodes);
    const tgtNode = nodeFromLink(link.target, data.nodes);
    if (!srcNode || !tgtNode) continue;
    const src = simNodes.find(item => item.id === srcNode.id);
    const tgt = simNodes.find(item => item.id === tgtNode.id);
    if (!src || !tgt) continue;

    simLinks.push({ source: src, target: tgt, type: link.type });
    const edgeType = link.type || "references";
    const color = new THREE.Color(edgeColor(edgeType));
    allPositions.push(src.x, src.y, src.z, tgt.x, tgt.y, tgt.z);
    allColors.push(color.r, color.g, color.b, color.r, color.g, color.b);
    edgeMeta.push({
      srcId: src.id,
      tgtId: tgt.id,
      type: edgeType,
      baseOpacity: edgeType === "contains" ? 0.22 : 0.42,
      baseColor: color.clone(),
    });
  }

  const edgeGeo = new THREE.BufferGeometry();
  edgeGeo.setAttribute("position", new THREE.Float32BufferAttribute(allPositions, 3));
  edgeGeo.setAttribute("color", new THREE.Float32BufferAttribute(allColors, 3));
  const edgeMat = new THREE.LineBasicMaterial({
    vertexColors: true,
    transparent: true,
    opacity: 0.95,
    depthWrite: false,
  });
  const allEdges = new THREE.LineSegments(edgeGeo, edgeMat);
  scene.add(allEdges);
  return { allEdges, edgeMeta, simLinks };
}

export function nodeScale(node: SimNode, maxDegree: number): number {
  const base = node.kind === "module" ? 3.4 : node.kind === "file" ? 2.5 : 1.8;
  return base + (node.degree / Math.max(1, maxDegree)) * 4.2;
}

export function maxNodeDegree(simNodes: SimNode[]): number {
  return Math.max(1, ...simNodes.map(node => node.degree));
}

export function applyNodeRiskStyles(
  nodeMeshes: Map<string, THREE.Mesh>,
  simNodes: SimNode[],
  risks: Record<string, NodeRisk>,
) {
  for (const node of simNodes) {
    const mesh = nodeMeshes.get(node.id);
    if (!mesh) continue;
    const risk = risks[node.id];
    const material = mesh.material as THREE.MeshStandardMaterial;
    const baseScale = mesh.userData.scale as number;
    node.risk_score = risk?.score || 0;
    node.risk_severity = risk?.severity;
    node.risk_categories = risk?.categories || [];
    material.emissive.setHex(risk ? riskColor(risk.severity) : nodeColor(node));
    material.emissiveIntensity = risk ? 0.55 + Math.min(0.5, risk.score / 180) : 0.25 + (mesh.userData.degRatio || 0) * 0.45;
    mesh.scale.setScalar(baseScale * (risk ? 1 + Math.min(0.34, risk.score / 260) : 1));
  }
}

function nodeColor(node: SimNode): number {
  return (CODEGRAPH_COLORS as Record<string, number>)[node.kind] || CODEGRAPH_COLORS.function;
}

function riskColor(severity: "P0" | "P1" | "P2"): number {
  if (severity === "P0") return 0xff4d6d;
  if (severity === "P1") return 0xfacc15;
  return 0x38bdf8;
}

function edgeColor(edgeType: string): number {
  return (CODEGRAPH_COLORS as Record<string, number>)[edgeType] || CODEGRAPH_COLORS.references;
}

function nodeFromLink(linkNode: string | GraphNode, nodes: GraphNode[]): GraphNode | undefined {
  return typeof linkNode === "string" ? nodes.find(node => node.id === linkNode) : linkNode;
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
