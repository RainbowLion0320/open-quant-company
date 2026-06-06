import * as THREE from "three";

export type CodeGraphTranslate = (key: string, params?: Record<string, any>) => string;
export type CodeGraphLevel = "module" | "file" | "symbol" | "neighborhood";

export interface CodeGraphStatus {
  initialized: boolean;
  file_count: number;
  node_count: number;
  edge_count: number;
  db_size_bytes?: number;
  backend?: string;
  languages: { language: string; files: number; nodes: number }[];
  nodes_by_kind: Record<string, number>;
  pending_changes: { added: number; modified: number; removed: number };
  stale: boolean;
  message?: string;
  truncated?: boolean;
}

export interface GraphNode {
  id: string;
  label: string;
  kind: string;
  path: string;
  qualified_name: string;
  language: string;
  start_line: number | null;
  end_line: number | null;
  count: number;
  degree: number;
  group: string;
  signature?: string | null;
  docstring?: string | null;
  risk_score?: number;
  risk_severity?: "P0" | "P1" | "P2";
  risk_categories?: string[];
  x?: number;
  y?: number;
  z?: number;
  vx?: number;
  vy?: number;
  vz?: number;
}

export interface NodeRisk {
  score: number;
  severity: "P0" | "P1" | "P2";
  categories: string[];
}

export interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  type: string;
  label: string;
  count: number;
  direction: string;
}

export interface GraphData {
  level: CodeGraphLevel;
  nodes: GraphNode[];
  links: GraphLink[];
  stats: CodeGraphStatus;
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

export const CODEGRAPH_COLORS = {
  module: 0x00d4ff,
  file: 0x2dd4bf,
  external_module: 0x64748b,
  class: 0xe8a840,
  function: 0x38bdf8,
  method: 0x60a5fa,
  component: 0xa78bfa,
  route: 0xf472b6,
  interface: 0x34d399,
  type_alias: 0xfacc15,
  imports: 0x7dd3fc,
  calls: 0xffffff,
  instantiates: 0xfbbf24,
  references: 0xa78bfa,
  extends: 0x34d399,
  contains: 0x475569,
} as const;

export const DEFAULT_EDGE_KINDS = ["imports", "calls", "instantiates", "references", "extends"] as const;
