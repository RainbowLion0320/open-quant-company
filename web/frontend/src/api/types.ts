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

export interface StrategyMeta {
  name: string;
  label: string;
  color: string;
  enabled: boolean;
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

export interface StrategySignal {
  strategy?: string;
  symbol: string;
  name: string;
  industry: string;
  score: number;
  signal: "buy" | "hold" | "sell";
  detail?: any;
  computed_at?: string;
}

export interface StrategyInfo {
  name: string;
  label: string;
  total: number;
  buys: number;
  last_computed: string;
}

export interface StrategiesResponse {
  strategies: StrategyInfo[];
  registry?: StrategyMeta[];
  total?: number;
  statuses?: string[];
}

export interface StrategyStatusItem {
  name: string;
  label: string;
  status: string;
  status_label: string;
  color: string;
}

export interface StrategyStatusesResponse {
  strategies: StrategyStatusItem[];
  statuses: string[];
  status_labels: Record<string, string>;
  status: string;
}

export interface StrategyGovernanceRole {
  name: string;
  layer: string;
  primary_use: string;
  description: string;
  allow_paper: boolean;
  allow_production: boolean;
}

export interface StrategyGovernanceResponse {
  roles: StrategyGovernanceRole[];
  stack: Record<string, string[]>;
  promotion_rules: Record<string, Record<string, number>>;
  status: string;
}

export interface StrategyCatalogItem {
  name: string;
  label: string;
  strategy_type: string;
  layer: string;
  lifecycle: string;
  data_requirements: string[];
  parameters?: Record<string, any>;
  output_contract: string;
  research_sources: string[];
}

export interface StrategyCatalogResponse {
  items: StrategyCatalogItem[];
  total: number;
}

export interface StrategyEvaluationSummary {
  baselines: string[];
  status: string;
  note: string;
}

export interface StrategyDetailResponse {
  signals: StrategySignal[];
}

export interface RunResponse {
  job_id: string;
}

export interface EquityPoint {
  date: string;
  value: number;
}

export interface BacktestOverview {
  start: string;
  end: string;
  bench_return: number;
  strategies: Record<string, {
    total_return: number;
    sharpe: number;
    max_drawdown: number;
    win_rate: number;
    trade_count: number;
  }>;
}

export interface BacktestDetail {
  equity_curve: EquityPoint[];
  bench_curve: EquityPoint[];
}

export interface PortfolioPosition {
  symbol: string;
  name: string;
  shares: number;
  cost: number;
  price: number;
  pnl: number;
  pnl_pct: number;
}

export interface PortfolioBalance {
  cash: number;
  total_value: number;
  total_pnl: number;
  total_pnl_pct: number;
}

export interface PortfolioNavPoint {
  date: string;
  total_asset: number;
  cash: number;
  market_value: number;
}

export interface PortfolioTrade {
  date: string;
  code: string;
  name: string;
  side: "buy" | "sell";
  price: number;
  volume: number;
  amount: number;
  strategy: string;
}

export interface PortfolioSummary {
  balance?: { total_asset: number; cash: number; market_value: number };
  total_return: number;
  total_return_pct: number;
  positions_count: number;
  position_value: number;
  peak_equity: number;
  nav_days: number;
}

export interface StockDetail {
  basic: { symbol: string; name: string; industry: string; sector: string; area: string; market: string };
  buffett?: { score: number; roe: number; gross_margin: number; debt_equity: number; dcf_value: number };
  kline?: KlinePoint[];
  signals?: Record<string, StrategySignal[]>;
  financials?: any[];
}

export interface StockListItem {
  symbol: string;
  name: string;
  industry: string;
  sector: string;
  price: number | null;
  change_pct: number | null;
  pe_ttm: number | null;
  pb: number | null;
  total_mv: number | null;
  buffett_score: number | null;
  roe: number | null;
  gross_margin: number | null;
  signal_score: number | null;
  signal: "buy" | "hold" | string;
  buy_signals: number;
  signal_count: number;
  top_strategy: string;
  updated_at: string;
}

export interface StockListResponse {
  stocks: StockListItem[];
  total: number;
  limit: number;
  updated_at: string;
}

export interface SignalChange {
  date: string;
  strategy: string;
  symbol: string;
  name: string;
  old_signal: string;
  new_signal: string;
}

export interface SystemMonitor {
  timestamp: string;
  cpu: { percent: number; freq_current: number | null; cores_physical: number; cores_logical: number; load_avg: number[] };
  memory: { total_gb: number; used_gb: number; percent: number };
  disk: { total_gb: number; used_gb: number; percent: number };
  battery: { percent: number; charging: boolean; minutes_left: number | null } | null;
  top_processes: { pid: number; name: string; cpu: number; mem: number }[];
  token: {
    hermes: { input_tokens: number; output_tokens: number; total_tokens: number; sessions: number; messages: number; tool_calls: number; api_calls: number; cost_usd: number };
    external: { input_tokens: number; output_tokens: number; total_tokens: number; calls: number; cost_usd: number; sources: string[] };
    total: { input_tokens: number; output_tokens: number; total_tokens: number; cost_usd: number };
    updated_at: string | null;
  };
}

export interface SystemHistoryResponse {
  hours: number;
  points: number;
  data: any[];
}

export interface DeepSeekUsageResponse {
  data: any[];
  source?: string;
  balance?: {
    status: string;
    is_available: boolean;
    balance_infos: { currency: string; total_balance: string; granted_balance: string; topped_up_balance: string }[];
    message?: string;
  };
  usage?: {
    status: string;
    daily: any[];
    models: string[];
    dates: string[];
    totals: { tokens: number; requests: number; estimated_cost_usd: number; estimated_cost_cny: number };
    pricing_source?: string;
  };
  total_cost?: number;
  status?: string;
  message?: string;
}

export interface SectorSignal {
  total: number;
  buy_count: number;
  buy_ratio: number;
  avg_score: number;
  top_symbol: string;
}

export interface SectorCard {
  sector_code: string;
  sector_name: string;
  rank: number;
  return_1d: number;
  return_5d: number;
  return_20d: number;
  return_60d: number;
  volatility: number;
  member_count: number;
  turnover_amount: number;
  amount_5d_avg: number;
  amount_share: number;
  amount_source: string;
  data_source: string;
  signals: Record<string, SectorSignal>;
}

export interface SectorOverviewResponse {
  sectors: SectorCard[];
  total_sectors: number;
  top_performers: SectorCard[];
  bottom_performers: SectorCard[];
  signal_dispersion: number;
  data_source: string;
  capital_source: string;
  freshness: { performance: string; signals: string };
}

export interface SectorExposureItem {
  sector: string;
  date: string;
  weight: number;
  market_value: number;
  position_count: number;
}

export interface SectorExposureResponse {
  exposure: SectorExposureItem[];
  total_sectors: number;
  data_source: string;
}

export interface SectorDetailResponse {
  sector_name: string;
  performance: Record<string, any>;
  signals: Record<string, SectorSignal>;
  data_source: string;
}

export interface DbHealthResponse {
  data: any[];
  summary: any | null;
  status: "ok" | "no_data" | "error";
  message?: string;
  checked_at?: string | null;
  api_fallback?: boolean;
}

export interface DbRepairResponse {
  status: "started" | "conflict" | "failed" | "not_found" | string;
  job_id?: string;
  table?: string;
  message?: string;
}

export interface HindsightGraphResponse {
  nodes: any[];
  links: any[];
  stats?: Record<string, any>;
}

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
