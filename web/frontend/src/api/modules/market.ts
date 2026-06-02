import { get } from "../client";
import type { MarketResponse, RegimeResponse, MarketRegimePipelineResponse } from "../types";

export const marketApi = {
  market: (range = "6M") => get<MarketResponse>(`/api/market?range=${encodeURIComponent(range)}`),
  marketRegime: () => get<RegimeResponse>("/api/market/regime"),
  marketRegimePipeline: () => get<MarketRegimePipelineResponse>("/api/pipeline/market-regime"),
  pipelineList: () => get<{ items: any[]; total: number }>("/api/pipeline"),
  pipelineShow: (key: string) => get<any>(`/api/pipeline/${key}`),
};
