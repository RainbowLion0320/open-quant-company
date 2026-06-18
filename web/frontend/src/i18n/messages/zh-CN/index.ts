import { app } from "./app";
import { common } from "./common";
import { errors } from "./errors";
import { nav } from "./nav";
import { ceoOffice } from "./ceoOffice";
import { modules } from "./modules";
import { market } from "./market";
import { pipeline } from "./pipeline";
import { portfolio } from "./portfolio";
import { sectors } from "./sectors";
import { stocks } from "./stocks";
import { stockDetail } from "./stockDetail";
import { settings } from "./settings";
import { strategies } from "./strategies";
import { signals } from "./signals";
import { backtest } from "./backtest";
import { evidence } from "./evidence";
import { database } from "./database";
import { assetCoverage } from "./assetCoverage";
import { dataSources } from "./dataSources";
import { activity } from "./activity";
import { configCenter } from "./configCenter";
import { codegraph } from "./codegraph";
import { testDesign } from "./testDesign";
import { astIntelligence } from "./astIntelligence";
import { lifecycle } from "./lifecycle";

export const zhCN = {
  app,
  common,
  errors,
  nav,
  ceoOffice,
  modules,
  market,
  pipeline,
  portfolio,
  sectors,
  stocks,
  stockDetail,
  settings,
  strategies,
  signals,
  backtest,
  evidence,
  database,
  assetCoverage,
  dataSources,
  activity,
  configCenter,
  codegraph,
  testDesign,
  astIntelligence,
  lifecycle,
} as const;
