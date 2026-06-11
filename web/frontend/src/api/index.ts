import { assetsApi } from "./modules/assets";
import { dataSourcesApi } from "./modules/dataSources";
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
  ...dataSourcesApi,
  ...portfolioApi,
  ...stocksApi,
  ...systemApi,
  ...settingsApi,
  ...sectorsApi,
};
