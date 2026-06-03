export interface RegimeBreadthDetail {
  advance_ratio?: number;
  above_ma20?: number;
  above_ma60?: number;
  above_ma120?: number;
  sample_size?: number;
  up_count?: number;
  down_count?: number;
  unchanged_count?: number;
  as_of?: string;
}

export interface RegimeScoreComponents {
  trend?: number;
  breadth?: number;
  risk?: number;
  volume?: number;
  trend_raw?: number;
  breadth_raw?: number;
  risk_raw?: number;
  volume_raw?: number;
  sample_size?: number;
  [key: string]: number | undefined;
}

export interface RegimeStability {
  raw_value?: "bull" | "bear" | "sideways" | "unknown" | "";
  confirmed_value?: "bull" | "bear" | "sideways" | "unknown" | "";
  pending_value?: "bull" | "bear" | "sideways" | "unknown" | "";
  pending_count?: number;
  min_dwell?: number;
  confirmed_changed?: boolean;
  score?: number;
  as_of?: string;
}

export type RegimeDetectionMethod = "rule_based" | "hmm" | "hybrid";
export type RegimeProbabilityMap = Partial<Record<"bull" | "sideways" | "bear", number>>;

export interface RegimeData {
  value: "bull" | "bear" | "sideways" | "unknown";
  raw_value?: "bull" | "bear" | "sideways" | "unknown";
  score?: number;
  ma_trend: string;
  volume_trend: string;
  breadth: number;
  breadth_detail?: RegimeBreadthDetail;
  score_components?: RegimeScoreComponents;
  stability?: RegimeStability;
  regime_probs?: RegimeProbabilityMap;
  detection_method?: RegimeDetectionMethod;
  hmm_confidence?: number;
  hmm_entropy?: number;
  decision_reason?: string;
}

export interface KlinePoint {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
}

export interface MarketSeriesPoint {
  date: string;
  value: number;
}

export interface MarketAssetCard {
  key: string;
  label: string;
  symbol: string;
  value: number | null;
  change: number;
  change_pct: number;
  unit: string;
  series: MarketSeriesPoint[];
  data_source: string;       // "real" | "proxy" | "placeholder" | "cached" | "missing"
  source_detail?: string;    // human-readable detail
}

export interface MacroCard {
  key: string;
  label: string;
  value: number | null;
  prev: number | null;
  unit: string;
  date: string;
  series: MarketSeriesPoint[];
}

export interface MarketAlert {
  level: "success" | "warning" | "danger" | "info";
  title: string;
  detail: string;
  time: string;
}

export interface PositionCapacity {
  current: number;
  max: number;
}

export interface MarketResponse {
  regime: RegimeData;
  kline: KlinePoint[];
  range?: string;
  multi_asset?: MarketAssetCard[];
  macro?: MacroCard[];
  freshness?: { market: string; macro: string };
  pool_size?: number;
  position_capacity?: PositionCapacity;
  config?: Record<string, any>;
  updated?: string;
}

export interface RegimeResponse {
  regime: RegimeData;
  multi_asset: MarketAssetCard[];
  freshness: { market: string };
  updated: string;
  config?: Record<string, any>;
  position_capacity?: PositionCapacity;
}
