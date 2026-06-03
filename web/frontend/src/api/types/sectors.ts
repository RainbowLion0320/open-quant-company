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
