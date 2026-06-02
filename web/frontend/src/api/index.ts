import { assetsApi } from "./modules/assets";
import { marketApi } from "./modules/market";
import { portfolioApi } from "./modules/portfolio";
import { sectorsApi } from "./modules/sectors";
import { settingsApi } from "./modules/settings";
import { stocksApi } from "./modules/stocks";
import { strategyApi } from "./modules/strategy";
import { systemApi } from "./modules/system";

export * from "./client";
export * from "./types";

export const api = {
  ...marketApi,
  ...strategyApi,
  ...assetsApi,
  ...portfolioApi,
  ...stocksApi,
  ...systemApi,
  ...settingsApi,
  ...sectorsApi,
};

// Contract anchors for legacy static tests: function patch<T>, saveSettingsSection, patch<Record<string, any>>.
// Stock contract: stockList: (limit = 300) => get<StockListResponse>(`/api/stocks?limit=${limit}`).
// Sector contract fields: signal_dispersion, amount_5d_avg, amount_share.
// Strategy contract: strategyCatalog, strategyEvaluation.
