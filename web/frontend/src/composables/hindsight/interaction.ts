import * as THREE from "three";
import { maxNodeDegree, nodeScale } from "./graphBuilder";
import { GraphNode, SimNode } from "./types";

export interface PickedGraphNode {
  node: SimNode;
  object: THREE.Object3D;
}

export function pickGraphNode(
  event: PointerEvent,
  container: HTMLElement,
  camera: THREE.PerspectiveCamera,
  nodeMeshes: Map<string, THREE.Mesh>,
  simNodes: SimNode[],
  raycaster: THREE.Raycaster,
  mouse: THREE.Vector2,
): PickedGraphNode | null {
  const rect = container.getBoundingClientRect();
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(mouse, camera);

  const intersects = raycaster.intersectObjects(Array.from(nodeMeshes.values()));
  if (!intersects.length) return null;
  const nodeId = intersects[0].object.userData.nodeId as string;
  const node = simNodes.find(item => item.id === nodeId);
  return node ? { node, object: intersects[0].object } : null;
}

export function graphNodePreview(node: SimNode): GraphNode {
  return {
    id: node.id,
    index: node.index,
    label: node.label,
    fullText: node.fullText || node.label,
    type: node.type,
    entities: node.entities,
    tags: node.tags,
    date: node.date,
    documentId: node.documentId || null,
    chunkId: node.chunkId || null,
    consolidatedAt: node.consolidatedAt || null,
    proofCount: node.proofCount,
    degree: node.degree,
  };
}

export function resetNodeScales(nodeMeshes: Map<string, THREE.Mesh>, simNodes: SimNode[]) {
  const maxDegree = maxNodeDegree(simNodes);
  for (const [id, mesh] of nodeMeshes) {
    const node = simNodes.find(item => item.id === id);
    mesh.scale.setScalar(node ? nodeScale(node, maxDegree) : 1.8);
  }
}
