import { computed, onMounted, onUnmounted, ref } from "vue";
import { api } from "../api";
import { useI18n } from "../i18n";

type ApiHealth = {
  items: { name: string; status: string; detail: string }[];
  summary: string;
  all_ok: boolean;
};

export function useActivityMonitor() {
  const { currentLocale, t } = useI18n();
  const apiHealth = ref<ApiHealth | null>(null);
  const cronJobs = ref<any[]>([]);
  const cronSummary = ref("");
  let refreshTimer: number | undefined;

  const API_HEALTH_ORDER = ["AKShare", "Tushare", "LLM:DeepSeek", "Telegram"];
  const apiHealthOrdered = computed(() => {
    if (!apiHealth.value) return [];
    const byName = new Map(apiHealth.value.items.map(item => [item.name, item]));
    const ordered = API_HEALTH_ORDER
      .map(name => byName.get(name))
      .filter(Boolean) as { name: string; status: string; detail: string }[];
    const known = new Set(API_HEALTH_ORDER);
    return ordered.concat(apiHealth.value.items.filter(item => !known.has(item.name)));
  });

  const cronSummaryBadge = computed(() => {
    if (!cronSummary.value) return "muted";
    return cronSummary.value.includes("err") ? "limited" : "ok";
  });

  function jobLabel(job: any): string {
    return job.name + (job.no_agent ? " [script]" : "");
  }

  function jobNextRun(job: any): string {
    if (!job.next_run) return "—";
    const next = new Date(job.next_run);
    const diffMin = Math.round((next.getTime() - Date.now()) / 60000);
    if (diffMin < 0) return t("activity.pending");
    if (diffMin < 60) return t("activity.inMinutes", { count: diffMin });
    if (diffMin < 1440) return t("activity.inHours", { count: Math.round(diffMin / 60) });
    return `${next.toLocaleDateString(currentLocale.value, { month: "short", day: "numeric" })} ${next.toLocaleTimeString(currentLocale.value, { hour: "2-digit", minute: "2-digit" })}`;
  }

  function jobLastRun(job: any): string {
    if (!job.last_run) return t("activity.never");
    const last = new Date(job.last_run);
    const diffMin = Math.round((Date.now() - last.getTime()) / 60000);
    const ago = diffMin < 60
      ? t("activity.agoMinutes", { count: diffMin })
      : diffMin < 1440
        ? t("activity.agoHours", { count: Math.round(diffMin / 60) })
        : last.toLocaleDateString(currentLocale.value, { month: "short", day: "numeric" });
    return `${ago} (${job.last_status || "—"})`;
  }

  function cronBadgeClass(status: string | null): string {
    if (!status) return "muted";
    return status === "ok" ? "ok" : "muted";
  }

  function apiBadgeClass(status: string): string {
    if (status === "ok") return "ok";
    if (status === "warn") return "limited";
    return "muted";
  }

  async function fetchApiHealth() {
    try {
      apiHealth.value = await api.apiHealth();
    } catch {
      apiHealth.value = null;
    }
  }

  async function fetchCronJobs() {
    try {
      const data = await api.cronJobs();
      cronJobs.value = data.jobs || [];
      cronSummary.value = data.summary || "";
    } catch {
      cronJobs.value = [];
      cronSummary.value = "";
    }
  }

  function refresh() {
    void fetchApiHealth();
    void fetchCronJobs();
  }

  onMounted(() => {
    refresh();
    refreshTimer = window.setInterval(refresh, 60_000);
  });

  onUnmounted(() => {
    if (refreshTimer) window.clearInterval(refreshTimer);
  });

  return {
    t,
    apiHealth,
    API_HEALTH_ORDER,
    apiHealthOrdered,
    cronJobs,
    cronSummary,
    cronSummaryBadge,
    jobLabel,
    jobNextRun,
    jobLastRun,
    cronBadgeClass,
    apiBadgeClass,
  };
}
