type TranslateFn = (key: string) => string;

export function signalLabel(signal: string, t: TranslateFn) {
  if (signal === "buy") return t("common.buy");
  if (signal === "sell") return t("common.sell");
  return t("common.hold");
}
