import { get, post } from "../client";
import type {
  BacktestDetail,
  BacktestOverview,
  RunResponse,
  StrategiesResponse,
  StrategyCatalogResponse,
  StrategyDetailResponse,
  StrategyEvaluationSummary,
  StrategyGovernanceResponse,
  StrategyStatusesResponse,
} from "../types";

export const strategyApi = {
  strategies: () => get<StrategiesResponse>("/api/strategies"),
  strategyStatuses: () => get<StrategyStatusesResponse>("/api/strategies/statuses"),
  strategyGovernance: () => get<StrategyGovernanceResponse>("/api/strategies/governance"),
  strategyCatalog: () => get<StrategyCatalogResponse>("/api/strategies/catalog"),
  strategyEvaluation: () => get<StrategyEvaluationSummary>("/api/strategies/evaluation"),
  strategyDetail: (name: string) => get<StrategyDetailResponse>(`/api/strategies/${name}`),
  strategyEvidence: () => get<{ items: any[]; total: number }>("/api/strategies/evidence"),
  strategyEvidenceDetail: (strategy: string) => get<any>(`/api/strategies/evidence/${strategy}`),
  strategyRun: (strategy: string, limit = 0, params?: any, mode: "production" | "research" = "production") =>
    post<RunResponse>("/api/strategies/run", { strategy, limit, params, mode }),
  backtest: () => get<BacktestOverview>("/api/backtest"),
  backtestDetail: (key: string) => get<BacktestDetail>(`/api/backtest/${key}`),
};
