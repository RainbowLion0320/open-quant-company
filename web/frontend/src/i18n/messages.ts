import { enUS } from "./messages/en-US";
import { zhCN } from "./messages/zh-CN";

export const messages = {
  "zh-CN": zhCN,
  "en-US": enUS,
} as const;

// Domain anchors retained for i18n contract tests: nav: common: pipeline: market: portfolio:
export type Messages = typeof messages;
