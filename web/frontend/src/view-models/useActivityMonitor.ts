import { ref, computed, onMounted, onUnmounted } from "vue";
import { api, type SystemMonitor } from "../api";
import { useI18n } from "../i18n";
import { fmtPercentValue } from "../utils/format";

export function useActivityMonitor() {

  const monitor = ref<SystemMonitor | null>(null);
  const { currentLocale, t } = useI18n();
  const monitorError = ref("");
  const lastFetch = ref(Date.now());
  const elapsed = ref(0);
  const historyHours = ref(24);
  let timer: number | undefined;
  let elapTimer: number | undefined;
  let slowTimer: number | undefined;

  const cpuColor = computed(() => {
    const p = monitor.value?.cpu?.percent ?? 0;
    if (p > 80) return "var(--negative)"; if (p > 50) return "var(--warning)"; return "var(--positive)";
  });
  const memColor = computed(() => {
    const p = monitor.value?.memory?.percent ?? 0;
    if (p > 85) return "var(--negative)"; if (p > 60) return "var(--warning)"; return "var(--positive)";
  });
  const loadText = computed(() => (monitor.value?.cpu?.load_avg ?? []).map(v => Number(v).toFixed(2)).join(" / ") || "—");
  const batteryText = computed(() => {
    const bat = monitor.value?.battery;
    if (!bat) return "—";
    return `${bat.percent ?? "—"}%${bat.charging ? ` · ${t("activity.charging")}` : ""}`;
  });

  const cpuChartId = "cpu-chart"; const memChartId = "mem-chart";
  const apiHealth = ref<{ items: { name: string; status: string; detail: string }[]; summary: string; all_ok: boolean } | null>(null);


  // Fixed API health display order: data → AI → infra → messaging
  const API_HEALTH_ORDER = ["AKShare", "Tushare", "LLM:DeepSeek", "Telegram"];
  const apiHealthOrdered = computed(() => {
    if (!apiHealth.value) return [];
    const byName = new Map(apiHealth.value.items.map(i => [i.name, i]));
    const ordered = API_HEALTH_ORDER.map(name => byName.get(name)).filter(Boolean) as { name: string; status: string; detail: string }[];
    const known = new Set(API_HEALTH_ORDER);
    return ordered.concat(apiHealth.value.items.filter(item => !known.has(item.name)));
  });

  // Cron jobs
  const cronJobs = ref<any[]>([]);
  const cronSummary = ref("");
  const cronSummaryBadge = computed(() => {
    if (!cronSummary.value) return "muted";
    return cronSummary.value.includes("err") ? "limited" : "ok";
  });

  function jobLabel(job: any): string {
    const tag = job.no_agent ? " [script]" : "";
    return job.name + tag;
  }
  function jobNextRun(job: any): string {
    if (!job.next_run) return "—";
    const d = new Date(job.next_run);
    const now = Date.now();
    const diffMin = Math.round((d.getTime() - now) / 60000);
    if (diffMin < 0) return t("activity.pending");
    if (diffMin < 60) return t("activity.inMinutes", { count: diffMin });
    if (diffMin < 1440) return t("activity.inHours", { count: Math.round(diffMin / 60) });
    return d.toLocaleDateString(currentLocale.value, { month: "short", day: "numeric" }) + " " + d.toLocaleTimeString(currentLocale.value, { hour: "2-digit", minute: "2-digit" });
  }
  function jobLastRun(job: any): string {
    if (!job.last_run) return t("activity.never");
    const d = new Date(job.last_run);
    const now = Date.now();
    const diffMin = Math.round((now - d.getTime()) / 60000);
    const ago = diffMin < 60 ? t("activity.agoMinutes", { count: diffMin }) : diffMin < 1440 ? t("activity.agoHours", { count: Math.round(diffMin / 60) }) : d.toLocaleDateString(currentLocale.value, { month: "short", day: "numeric" });
    const st = job.last_status || "—";
    return `${ago} (${st})`;
  }
  function cronBadgeClass(st: string | null): string {
    if (!st) return "muted";
    if (st === "ok") return "ok";
    if (st === "error") return "muted";
    return "muted";
  }

  async function fetchCronJobs() {
    try {
      const data = await api.cronJobs();
      cronJobs.value = data.jobs || [];
      cronSummary.value = data.summary || "";
    } catch { cronJobs.value = []; cronSummary.value = ""; }
  }

  function apiBadgeClass(status: string): string {
    if (status === "ok") return "ok";
    if (status === "warn") return "limited";
    if (status === "error" || status === "missing") return "muted";
    if (status === "disabled" || status === "unknown") return "muted";
    return "muted";
  }


  async function fetchApiHealth() {
    try { apiHealth.value = await api.apiHealth(); } catch { apiHealth.value = null; }
  }

  function fmtGb(v: number | undefined | null): string {
    if (v == null || Number.isNaN(Number(v))) return "— GB";
    return `${Number(v).toFixed(1)} GB`;
  }
  function fmtPercent(v: number | undefined | null): string {
    return fmtPercentValue(v);
  }
  function pctWidth(v: number | undefined | null): string {
    return `${Math.max(0, Math.min(100, Number(v || 0)))}%`;
  }

  async function fetchData() {
    try {
      monitorError.value = "";
      const next = await api.systemMonitor();
      monitor.value = (next as any).status === "no_data" ? null : next;
      lastFetch.value = Date.now();
    } catch (e: any) {
      monitorError.value = e?.message || t("activity.retryError");
    }
  }

  function fetchSlowData() {
    drawCharts();
  }

  function drawCharts() {
    const charts = [
      { id: cpuChartId, key: "cpu_pct" as const, color: "#06b6d4", max: 100 },
      { id: memChartId, key: "mem_pct" as const, color: "#10b981", max: 100 },
    ];
    api.systemHistory(historyHours.value).then(hist => {
      const pts = hist.data || [];
      for (const ch of charts) {
        const canvas = document.getElementById(ch.id) as HTMLCanvasElement;
        if (!canvas) continue;
        const ctx = canvas.getContext("2d");
        if (!ctx) continue;
        const width = canvas.offsetWidth || 240;
        const height = canvas.offsetHeight || 112;
        canvas.width = width * 2;
        canvas.height = height * 2;
        ctx.scale(2, 2);
        const W = width, H = height;
        ctx.clearRect(0, 0, W, H);
        if (pts.length < 2) continue;
        const vals = pts.map((p: any) => p[ch.key] || 0);
        const maxVal = ch.max || Math.max(...vals, 1);
        ctx.beginPath();
        ctx.strokeStyle = ch.color;
        ctx.lineWidth = 1.5;
        for (let i = 0; i < vals.length; i++) {
          const x = (i / (vals.length - 1)) * (W - 10) + 5;
          const y = H - (vals[i] / maxVal) * (H - 10) - 5;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
    }).catch(() => {});
  }

  onMounted(() => {
    fetchData();
    fetchSlowData();
    fetchApiHealth();
    fetchCronJobs();
    timer = window.setInterval(fetchData, 10_000);
    slowTimer = window.setInterval(fetchSlowData, 60_000);
    elapTimer = window.setInterval(() => { elapsed.value = Math.round((Date.now() - lastFetch.value) / 1000); }, 1000);
  });
  onUnmounted(() => {
    if (timer) clearInterval(timer);
    if (slowTimer) clearInterval(slowTimer);
    if (elapTimer) clearInterval(elapTimer);
  });

  return {
    monitor,
    currentLocale,
    t,
    monitorError,
    lastFetch,
    elapsed,
    historyHours,
    cpuColor,
    memColor,
    loadText,
    batteryText,
    cpuChartId,
    memChartId,
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
    fetchCronJobs,
    apiBadgeClass,
    fetchApiHealth,
    fmtGb,
    fmtPercent,
    pctWidth,
    fetchData,
    fetchSlowData,
    drawCharts,
  };
}
