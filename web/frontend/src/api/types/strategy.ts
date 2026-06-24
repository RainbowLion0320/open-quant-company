export interface StrategyMeta {
  name: string;
  label: string;
  color: string;
  enabled: boolean;
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
  config_key: string;
  data_requirements: string[];
  asset_scope: string[];
  required_asset_dimensions: string[];
  paper_supported: boolean;
  live_supported: boolean;
  blockers: string[];
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

export interface StrategyDataCoverageFamily {
  key: string;
  label_zh: string;
  label_en: string;
}

export interface StrategyDataCoverageAsset {
  key: string;
  label_zh: string;
  label_en: string;
}

export interface StrategyDataCoverageCell {
  status: "declared" | "observed" | "required_missing" | "optional_missing" | "not_applicable" | string;
  declared: boolean;
  observed: boolean;
  expectation: "required" | "optional" | "not_applicable" | string;
}

export interface StrategyDataCoverageRow {
  strategy: string;
  label: string;
  strategy_type: string;
  layer: string;
  lifecycle: string;
  declared_dimensions: string[];
  asset_scope: string[];
  required_asset_dimensions: string[];
  paper_supported: boolean;
  live_supported: boolean;
  blockers: string[];
  declared_families: string[];
  observed_dimensions: string[];
  observed_families: string[];
  observed_status: string;
  required_families: string[];
  optional_families: string[];
  not_applicable_families: string[];
  missing_required_families: string[];
  optional_missing_families: string[];
  unused_declared_families: string[];
  missing_required_assets: string[];
  coverage_score: number;
  cells: Record<string, StrategyDataCoverageCell>;
  asset_cells: Record<string, StrategyDataCoverageCell>;
}

export interface StrategyDataCoverageResponse {
  status: string;
  generated_at: string;
  recommended_command: string;
  families: StrategyDataCoverageFamily[];
  assets: StrategyDataCoverageAsset[];
  expectations: Record<string, any>;
  summary: {
    strategy_count: number;
    family_count: number;
    required_gap_count: number;
    optional_gap_count: number;
    asset_gap_count: number;
    missing_observed_count: number;
  };
  rows: StrategyDataCoverageRow[];
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
