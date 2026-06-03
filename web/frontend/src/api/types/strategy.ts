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
