import * as THREE from "three";

export type HindsightTranslate = (key: string, params?: Record<string, any>) => string;

export interface GraphNode {
  id: string;
  index: number;
  label: string;
  fullText: string;
  type: "observation" | "experience" | "world";
  entities: string[];
  tags: string[];
  date: string;
  documentId: string | null;
  chunkId: string | null;
  consolidatedAt: string | null;
  proofCount: number;
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
  degree?: number;
}

export interface GraphLink {
  source: number | GraphNode;
  target: number | GraphNode;
  type: string;
  label: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  stats?: { total_nodes: number; total_links: number; last_consolidated: string };
}

export interface SimNode extends GraphNode {
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  fx?: number | null;
  fy?: number | null;
  fz?: number | null;
  degree: number;
}

export interface SimLink {
  source: SimNode;
  target: SimNode;
  type: string;
}

export interface EdgeMeta {
  srcId: string;
  tgtId: string;
  type: string;
  baseOpacity: number;
  baseColor: THREE.Color;
}

export const HINDSIGHT_COLORS = {
  obs: 0x00d4ff,
  exp: 0x7c3aed,
  world: 0xe8a840,
  semantic: 0x00d4ff,
  temporal: 0x64748b,
  consolidation: 0x00ffc8,
  tag: 0x7c3aed,
} as const;
