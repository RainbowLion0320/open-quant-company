import * as THREE from "three";
import { EdgeMeta, SimLink, SimNode } from "./types";

export function tickForceLayout(simNodes: SimNode[], simLinks: SimLink[]): number {
  const centering = 0.003;
  const damping = 0.85;
  const repulsion = 400;
  const springLen = 45;
  const springK = 0.003;

  for (const node of simNodes) {
    if (node.fx != null) continue;
    for (const other of simNodes) {
      if (node === other) continue;
      const dx = node.x - other.x;
      const dy = node.y - other.y;
      const dz = node.z - other.z;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy + dz * dz), 1);
      const force = repulsion / (dist * dist);
      node.vx += (dx / dist) * force;
      node.vy += (dy / dist) * force;
      node.vz += (dz / dist) * force;
    }
    node.vx = (node.vx - node.x * centering) * damping;
    node.vy = (node.vy - node.y * centering) * damping;
    node.vz = (node.vz - node.z * centering) * damping;
    node.x += node.vx;
    node.y += node.vy;
    node.z += node.vz;
  }

  for (const link of simLinks) {
    const source = link.source;
    const target = link.target;
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const dz = target.z - source.z;
    const dist = Math.max(Math.sqrt(dx * dx + dy * dy + dz * dz), 1);
    const disp = (dist - springLen) * springK;
    const fx = (dx / dist) * disp;
    const fy = (dy / dist) * disp;
    const fz = (dz / dist) * disp;
    if (source.fx == null) {
      source.vx += fx;
      source.vy += fy;
      source.vz += fz;
    }
    if (target.fx == null) {
      target.vx -= fx;
      target.vy -= fy;
      target.vz -= fz;
    }
  }

  return simNodes.reduce((maxSpeed, node) => {
    if (node.fx != null) return maxSpeed;
    const speed = Math.sqrt(node.vx * node.vx + node.vy * node.vy + node.vz * node.vz);
    return Math.max(maxSpeed, speed);
  }, 0);
}

export function syncNodeMeshes(simNodes: SimNode[], nodeMeshes: Map<string, THREE.Mesh>) {
  for (const node of simNodes) {
    const mesh = nodeMeshes.get(node.id);
    if (mesh) mesh.position.set(node.x, node.y, node.z);
  }
}

export function updateEdgePositions(
  allEdges: THREE.LineSegments | null,
  edgeMeta: EdgeMeta[],
  simNodes: SimNode[],
) {
  if (!allEdges) return;
  const positions = allEdges.geometry.attributes.position.array as Float32Array;
  for (let i = 0; i < edgeMeta.length; i++) {
    const { srcId, tgtId } = edgeMeta[i];
    const src = simNodes.find(node => node.id === srcId);
    const tgt = simNodes.find(node => node.id === tgtId);
    const offset = i * 6;
    if (src && tgt) {
      positions[offset] = src.x;
      positions[offset + 1] = src.y;
      positions[offset + 2] = src.z;
      positions[offset + 3] = tgt.x;
      positions[offset + 4] = tgt.y;
      positions[offset + 5] = tgt.z;
    }
  }
  allEdges.geometry.attributes.position.needsUpdate = true;
}

export function highlightGraphEdges(allEdges: THREE.LineSegments | null, edgeMeta: EdgeMeta[], nodeId: string | null) {
  if (!allEdges) return;
  const colors = allEdges.geometry.attributes.color.array as Float32Array;
  const material = allEdges.material as THREE.LineBasicMaterial;
  const dim = new THREE.Color(0x111122);
  const inbound = new THREE.Color(0x22d3ee);
  const outbound = new THREE.Color(0xfacc15);

  for (let i = 0; i < edgeMeta.length; i++) {
    const meta = edgeMeta[i];
    let color = meta.baseColor;
    if (nodeId) {
      if (meta.srcId === nodeId) color = outbound;
      else if (meta.tgtId === nodeId) color = inbound;
      else color = dim;
    }
    const offset = i * 6;
    colors[offset] = color.r;
    colors[offset + 1] = color.g;
    colors[offset + 2] = color.b;
    colors[offset + 3] = color.r;
    colors[offset + 4] = color.g;
    colors[offset + 5] = color.b;
  }
  material.opacity = 1.0;
  allEdges.geometry.attributes.color.needsUpdate = true;
}

export function pulseSelectedEdges(
  allEdges: THREE.LineSegments | null,
  edgeMeta: EdgeMeta[],
  nodeId: string | null,
  timestamp: number,
) {
  if (!allEdges || !nodeId) return;
  const colors = allEdges.geometry.attributes.color.array as Float32Array;
  const inbound = new THREE.Color(0x22d3ee);
  const outbound = new THREE.Color(0xfacc15);
  const white = new THREE.Color(0xffffff);
  const pulse = (Math.sin(timestamp / 180) + 1) / 2;

  for (let i = 0; i < edgeMeta.length; i++) {
    const meta = edgeMeta[i];
    if (meta.srcId !== nodeId && meta.tgtId !== nodeId) continue;
    const base = meta.srcId === nodeId ? outbound : inbound;
    const color = base.clone().lerp(white, 0.22 + pulse * 0.45);
    const offset = i * 6;
    colors[offset] = color.r;
    colors[offset + 1] = color.g;
    colors[offset + 2] = color.b;
    colors[offset + 3] = color.r;
    colors[offset + 4] = color.g;
    colors[offset + 5] = color.b;
  }
  allEdges.geometry.attributes.color.needsUpdate = true;
}
