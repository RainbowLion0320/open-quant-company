import { computed, reactive, ref, onMounted } from "vue";
import { api } from "../api";
import { hasAuthToken } from "../api/client";
import { useI18n } from "../i18n";
import { fmtConfigRatio } from "../utils/format";

export function useSettingsView() {

  const { t } = useI18n();
  const settings = reactive<Record<string, any>>({});
  const authStatus = ref<Record<string, any>>({});
  const strategyStatuses = ref<{ name: string; label: string; status: string; status_label: string; color: string }[]>([]);

  const apiKeyStatus = computed(() => {
    if (hasAuthToken()) return t("settings.apiKeySessionSet");
    const has = authStatus.value?.has_api_key;
    if (has === undefined) return t("settings.checking");
    return has ? t("settings.apiKeyRequired") : t("settings.apiKeyOpen");
  });

  const risk = computed(() => settings.risk_control || {});
  const hasRiskConfig = computed(() => Object.keys(risk.value).length > 0 && Object.values(risk.value).some((v: any) => v?.enabled));
  const notificationText = computed(() => {
    const enabled = settings.trading?.notification?.enabled ? t("common.enabled") : t("common.disabled");
    const changeOnly = settings.trading?.notification?.signal_change_only !== false ? t("settings.signalChangeOnly") : t("settings.allSignals");
    return `Telegram ${enabled} · ${changeOnly}`;
  });
  const sourceItems = computed(() => {
    const registry = settings.data_registry || {};
    const grouped: Record<string, { name: string; total: number; enabled: number; status: string }> = {};
    const labels: Record<string, string> = {
      akshare: "AKShare",
      tushare_free: "Tushare Free",
      tushare_mcp: "Tushare MCP",
      parquet: "Parquet",
      duckdb: "DuckDB",
    };
    for (const entry of Object.values(registry) as any[]) {
      const key = String(entry?.source || "local");
      grouped[key] = grouped[key] || { name: labels[key] || key, total: 0, enabled: 0, status: "available" };
      grouped[key].total += 1;
      if (entry?.enabled !== false) grouped[key].enabled += 1;
      if (entry?.enabled !== false && entry?.status && entry.status !== "available") grouped[key].status = String(entry.status);
    }
    return Object.values(grouped)
      .sort((a, b) => b.enabled - a.enabled || a.name.localeCompare(b.name))
      .slice(0, 6)
      .map(item => ({ ...item, summary: item.enabled ? `${item.enabled}/${item.total} dims` : t("common.disabled") }));
  });

  function fmtPct(v: number | undefined): string {
    return fmtConfigRatio(v);
  }
  async function fetchStrategyStatuses() {
    try {
      const data = await api.strategyStatuses();
      strategyStatuses.value = data.strategies || [];
    } catch {}
  }

  function sourceBadgeClass(status: string): string {
    if (status === "available") return "badge-green";
    if (status === "rate_limited") return "badge-amber";
    return "badge-muted";
  }

  function statusBadgeClass(status: string): string {
    if (status === "production") return "badge-green";
    if (status === "paper") return "badge-amber";
    if (status === "candidate") return "badge-blue";
    return "badge-muted";
  }

  async function loadAuthStatus() {
    try {
      authStatus.value = await api.authStatus();
    } catch {}
  }

  onMounted(async () => {
    try {
      const data = await api.settings();
      Object.assign(settings, data);
    } catch {}
    await loadAuthStatus();
    fetchStrategyStatuses();
  });

  return {
    t,
    settings,
    authStatus,
    strategyStatuses,
    apiKeyStatus,
    risk,
    hasRiskConfig,
    notificationText,
    sourceItems,
    fmtPct,
    fetchStrategyStatuses,
    sourceBadgeClass,
    statusBadgeClass,
    loadAuthStatus,
  };
}
