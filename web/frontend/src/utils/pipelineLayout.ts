import ELK, { type ElkNode, type ElkPoint } from "elkjs/lib/elk.bundled";

export interface PipelineLayoutNode {
  id: string;
  width: number;
  height: number;
}

export interface PipelineLayoutEdge {
  source: string;
  target: string;
  label?: string;
  condition?: string;
  active?: boolean;
}

export interface PipelineNodePosition {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PipelineEdgePath {
  id: string;
  source: string;
  target: string;
  active: boolean;
  label: string;
  points: ElkPoint[];
  d: string;
  labelX: number;
  labelY: number;
}

export interface PipelineLayoutResult {
  width: number;
  height: number;
  nodes: PipelineNodePosition[];
  edges: PipelineEdgePath[];
}

export interface PipelineLayoutOptions {
  nodeSpacing?: number;
  layerSpacing?: number;
}

const elk = new ELK();

const FALLBACK_NODE_WIDTH = 176;
const FALLBACK_NODE_HEIGHT = 112;

export async function layoutPipelineGraph(
  nodes: PipelineLayoutNode[],
  edges: PipelineLayoutEdge[],
  options: PipelineLayoutOptions = {},
): Promise<PipelineLayoutResult> {
  const graph: ElkNode = {
    id: "pipeline",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "DOWN",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.spacing.nodeNode": String(options.nodeSpacing ?? 34),
      "elk.layered.spacing.nodeNodeBetweenLayers": String(options.layerSpacing ?? 104),
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
      "elk.layered.nodePlacement.strategy": "BRANDES_KOEPF",
      "elk.layered.nodePlacement.favorStraightEdges": "false",
      "elk.layered.nodePlacement.bk.fixedAlignment": "BALANCED",
      "elk.layered.considerModelOrder.strategy": "PREFER_EDGES",
      "elk.layered.mergeEdges": "true",
      "elk.spacing.edgeEdge": "10",
      "elk.spacing.edgeNode": "16",
    },
    children: nodes.map((node) => ({
      id: node.id,
      width: node.width || FALLBACK_NODE_WIDTH,
      height: node.height || FALLBACK_NODE_HEIGHT,
    })),
    edges: edges.map((edge, index) => ({
      id: edgeId(edge, index),
      sources: [edge.source],
      targets: [edge.target],
    })),
  };

  const result = await elk.layout(graph);
  const layoutNodes = balanceLayerCenters((result.children || []).map((node) => ({
    id: node.id,
    x: node.x || 0,
    y: node.y || 0,
    width: node.width || FALLBACK_NODE_WIDTH,
    height: node.height || FALLBACK_NODE_HEIGHT,
  })));

  return {
    width: result.width || 0,
    height: result.height || 0,
    nodes: layoutNodes,
    edges: routePipelineEdges(layoutNodes, edges),
  };
}

export function visiblePipelineEdges(
  edges: PipelineEdgePath[],
  selectedNodeId: string,
  showInactiveEdges = false,
): PipelineEdgePath[] {
  return edges.filter((edge) => (
    edge.active ||
    showInactiveEdges ||
    edge.source === selectedNodeId ||
    edge.target === selectedNodeId
  ));
}

export function offsetPipelineEdgePath(edge: PipelineEdgePath, dx: number, dy: number): PipelineEdgePath {
  const points = edge.points.map((point) => ({ x: point.x + dx, y: point.y + dy }));
  return {
    ...edge,
    points,
    d: pathFromPoints(points),
    labelX: edge.labelX + dx,
    labelY: edge.labelY + dy,
  };
}

function edgeId(edge: PipelineLayoutEdge, index: number) {
  return `${edge.source}->${edge.target}:${index}`;
}

function balanceLayerCenters(nodes: PipelineNodePosition[]) {
  if (!nodes.length) return nodes;

  const layoutWidth = Math.max(...nodes.map((node) => node.x + node.width), FALLBACK_NODE_WIDTH);
  const layoutCenter = layoutWidth / 2;
  const rows: PipelineNodePosition[][] = [];

  for (const node of [...nodes].sort((a, b) => a.y - b.y || a.x - b.x)) {
    const row = rows.find((candidate) => Math.abs(candidate[0].y - node.y) < 24);
    if (row) row.push(node);
    else rows.push([node]);
  }

  const shifts = new Map<string, number>();
  for (const row of rows) {
    const minX = Math.min(...row.map((node) => node.x));
    const maxX = Math.max(...row.map((node) => node.x + node.width));
    const centeredShift = layoutCenter - (minX + maxX) / 2;
    const clampedShift = Math.max(-minX, Math.min(centeredShift, layoutWidth - maxX));
    for (const node of row) shifts.set(node.id, clampedShift);
  }

  return nodes.map((node) => ({
    ...node,
    x: node.x + (shifts.get(node.id) || 0),
  }));
}

function routePipelineEdges(
  nodes: PipelineNodePosition[],
  edges: PipelineLayoutEdge[],
): PipelineEdgePath[] {
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const outgoing = edgeBuckets(edges, "source");
  const incoming = edgeBuckets(edges, "target");

  return edges.map((edge, index) => {
    const source = nodeMap.get(edge.source);
    const target = nodeMap.get(edge.target);
    const points = source && target
      ? orthogonalRoute(
        source,
        target,
        edgePortIndex(outgoing.get(edge.source) || [], index),
        (outgoing.get(edge.source) || []).length,
        edgePortIndex(incoming.get(edge.target) || [], index),
        (incoming.get(edge.target) || []).length,
      )
      : [];
    const labelPoint = midpoint(points);

    return {
      id: edgeId(edge, index),
      source: edge.source,
      target: edge.target,
      active: edge.active !== false,
      label: edge.label || edge.condition || "",
      points,
      d: pathFromPoints(points),
      labelX: labelPoint.x,
      labelY: labelPoint.y,
    };
  });
}

function orthogonalRoute(
  source: PipelineNodePosition,
  target: PipelineNodePosition,
  sourceIndex: number,
  sourceCount: number,
  targetIndex: number,
  targetCount: number,
) {
  const sourceRatio = sourceCount > 1 ? (sourceIndex + 1) / (sourceCount + 1) : 0.5;
  const targetRatio = targetCount > 1 ? (targetIndex + 1) / (targetCount + 1) : 0.5;
  const x1 = source.x + source.width * sourceRatio;
  const y1 = source.y + source.height;
  const x2 = target.x + target.width * targetRatio;
  const y2 = target.y;

  if (Math.abs(x1 - x2) < 2) {
    return [{ x: x1, y: y1 }, { x: x2, y: y2 }];
  }

  const midY = y2 > y1 ? y1 + (y2 - y1) / 2 : y1 + 28;
  return [
    { x: x1, y: y1 },
    { x: x1, y: midY },
    { x: x2, y: midY },
    { x: x2, y: y2 },
  ];
}

function edgeBuckets(edges: PipelineLayoutEdge[], key: "source" | "target") {
  const buckets = new Map<string, number[]>();
  edges.forEach((edge, index) => {
    const id = edge[key];
    if (!buckets.has(id)) buckets.set(id, []);
    buckets.get(id)!.push(index);
  });
  return buckets;
}

function edgePortIndex(bucket: number[], edgeIndex: number) {
  const index = bucket.indexOf(edgeIndex);
  return index < 0 ? 0 : index;
}

function pathFromPoints(points: ElkPoint[]) {
  if (points.length < 2) return "";
  const [first, ...rest] = points;
  return `M${first.x} ${first.y}${rest.map((point) => `L${point.x} ${point.y}`).join("")}`;
}

function midpoint(points: ElkPoint[]) {
  if (!points.length) return { x: 0, y: 0 };
  if (points.length === 1) return points[0];

  const middleIndex = Math.floor((points.length - 1) / 2);
  const start = points[middleIndex];
  const end = points[middleIndex + 1] || start;
  return {
    x: (start.x + end.x) / 2,
    y: (start.y + end.y) / 2,
  };
}
