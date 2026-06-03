export interface PipelineMetric {
  label: string;
  value: string | number;
  tone?: "neutral" | "accent" | "positive" | "warning" | "negative" | string;
}

export interface PipelineNode {
  id: "inputs" | "features" | "rule_score" | "hmm_inference" | "hybrid_decision" | "stability" | "outputs" | string;
  title: string;
  subtitle: string;
  status: "ready" | "fallback" | "warning" | string;
  metrics: PipelineMetric[];
  inputs: string[];
  outputs: string[];
}

export interface PipelineEdge {
  source: string;
  target: string;
  label?: string;
}

export interface MarketRegimePipelineResponse {
  pipeline_key: "market_regime";
  updated: string;
  summary: {
    confirmed_regime: string;
    raw_regime: string;
    score: number;
    engine: string;
    detection_method: string;
    decision_reason?: string;
    confidence: number;
    entropy: number;
    adaptive_params?: Record<string, number | string>;
  };
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  warnings: string[];
}
