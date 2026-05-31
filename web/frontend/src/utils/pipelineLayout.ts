export interface PipelineLayoutNode {
  id: string;
}

export interface PipelineLayoutEdge {
  source: string;
  target: string;
}

export interface PipelineNodePosition {
  row: number;
  col: number;
  id: string;
}

export function buildPipelineLayout(
  nodes: PipelineLayoutNode[],
  edges: PipelineLayoutEdge[],
): PipelineNodePosition[] {
  if (!nodes.length) return [];

  const inDegree = new Map<string, number>();
  const children = new Map<string, string[]>();
  for (const node of nodes) {
    inDegree.set(node.id, 0);
    children.set(node.id, []);
  }
  for (const edge of edges) {
    inDegree.set(edge.target, (inDegree.get(edge.target) || 0) + 1);
    children.get(edge.source)?.push(edge.target);
  }

  const depth = new Map<string, number>();
  const queue: string[] = [];
  for (const node of nodes) {
    depth.set(node.id, 0);
    if ((inDegree.get(node.id) || 0) === 0) queue.push(node.id);
  }
  while (queue.length) {
    const current = queue.shift()!;
    for (const child of children.get(current) || []) {
      depth.set(child, Math.max(depth.get(child) || 0, (depth.get(current) || 0) + 1));
      inDegree.set(child, (inDegree.get(child) || 0) - 1);
      if (inDegree.get(child) === 0) queue.push(child);
    }
  }

  const rowGroups = new Map<number, string[]>();
  for (const node of nodes) {
    const row = depth.get(node.id) || 0;
    if (!rowGroups.has(row)) rowGroups.set(row, []);
    rowGroups.get(row)!.push(node.id);
  }

  const positions: PipelineNodePosition[] = [];
  for (const [row, ids] of [...rowGroups.entries()].sort((a, b) => a[0] - b[0])) {
    ids.forEach((id, col) => positions.push({ row, col, id }));
  }
  return positions;
}
