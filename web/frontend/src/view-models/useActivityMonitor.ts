import { ref, computed, nextTick, onMounted, onUnmounted, type ComponentPublicInstance } from "vue";
import { api, type SystemMonitor } from "../api";
import { useI18n } from "../i18n";
import { fmtPercentValue, fmtShortCount } from "../utils/format";

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
  const llmModelRefs = ref<Record<string, HTMLCanvasElement | null>>({});
  const llmCostRef = ref<HTMLCanvasElement | null>(null);
  const llmHasUsage = ref(false);
  const llmChartSeries = ref<{ key: string; label: string }[]>([]);
  const llmTotals = ref<{
    tokens: number;
    requests: number;
    costCny: number;
    costUsd: number;
    balanceText: string;
    balanceStatus: string;
    pricingStatus: string;
    unpricedRows: number;
    unpricedReasons: string[];
  } | null>(null);

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

  function setLlmModelCanvas(modelKey: string, el: Element | ComponentPublicInstance | null): void {
    llmModelRefs.value[modelKey] = typeof HTMLCanvasElement !== "undefined" && el instanceof HTMLCanvasElement ? el : null;
  }

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

  function fmtNum(n: number): string {
    return fmtShortCount(n);
  }
  function fmtMoney(n: number, currency: string): string {
    if (!Number.isFinite(Number(n))) return "—";
    const prefix = currency === "CNY" ? "¥" : "$";
    return `${prefix}${Number(n).toFixed(Number(n) >= 100 ? 0 : 2)}`;
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
    drawLlmUsageChart();
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

  async function drawLlmUsageChart() {
    try {
      const d = await api.llmUsage();
      const rows: any[] = d.usage?.daily || d.data || [];
      llmHasUsage.value = rows.length > 0;
      const balances = d.balances && typeof d.balances === "object" ? Object.values(d.balances) as any[] : [];
      const providerBalance = d.balance || balances[0];
      const balance = providerBalance?.balance_infos?.[0];
      const balanceText = balance
        ? fmtMoney(Number(balance.total_balance || 0), balance.currency || "CNY")
        : "—";
      const balanceStatus = providerBalance?.status === "ok"
        ? (providerBalance?.is_available ? "available" : "unavailable")
        : (providerBalance?.message || providerBalance?.status || "missing");
      const providers = Array.from(new Set(rows.map((r: any) => String(r.provider || "").trim()).filter(Boolean)));
      const chartKey = (row: any) => `${String(row.provider || "default")}::${String(row.model || "unknown")}`;
      const chartLabel = (key: string) => {
        const [provider, model] = key.split("::");
        return providers.length > 1 ? `${provider}:${model}` : model;
      };
      const tokenTotal = (row: any) => {
        const hit = Number(row.input_cache_hit || 0);
        const miss = Number(row.input_cache_miss || Math.max(Number(row.input_tokens || 0) - hit, 0));
        return hit + miss + Number(row.output_tokens || 0);
      };
      const seriesTotals = new Map<string, number>();
      for (const row of rows) {
        const key = chartKey(row);
        seriesTotals.set(key, (seriesTotals.get(key) || 0) + tokenTotal(row));
      }
      llmChartSeries.value = Array.from(seriesTotals.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 4)
        .map(([key]) => ({ key, label: chartLabel(key) }));

      if (!rows.length) {
        llmChartSeries.value = [];
        llmTotals.value = {
          tokens: d.usage?.totals?.tokens || 0,
          requests: d.usage?.totals?.requests || 0,
          costCny: d.usage?.totals?.estimated_cost_cny || 0,
          costUsd: d.usage?.totals?.estimated_cost_usd || 0,
          balanceText,
          balanceStatus,
          pricingStatus: d.usage?.pricing_status || "ok",
          unpricedRows: Number(d.usage?.unpriced_rows || 0),
          unpricedReasons: d.usage?.unpriced_reasons || [],
        };
        return;
      }
      await nextTick();
      const dates = Array.from(new Set(rows.map((r: any) => String(r.utc_date || "").slice(0, 10)).filter(Boolean))).sort();
      if (!dates.length) return;
      const rowByDate: Record<string, any> = {};
      for (const r of rows) {
        const date = String(r.utc_date || "").slice(0, 10);
        if (!date) continue;
        const key = date + "|" + chartKey(r);
        const existing = rowByDate[key] || {};
        rowByDate[key] = {
          ...existing,
          ...r,
          input_cache_hit: Number(existing.input_cache_hit || 0) + Number(r.input_cache_hit || 0),
          input_cache_miss: Number(existing.input_cache_miss || 0) + Number(r.input_cache_miss || Math.max(Number(r.input_tokens || 0) - Number(r.input_cache_hit || 0), 0)),
          output_tokens: Number(existing.output_tokens || 0) + Number(r.output_tokens || 0),
          total_tokens: Number(existing.total_tokens || 0) + Number(r.total_tokens || tokenTotal(r)),
        };
      }
      llmTotals.value = {
        tokens: d.usage?.totals?.tokens || rows.reduce((s: number, r: any) => s + (r.total_tokens||0), 0),
        requests: d.usage?.totals?.requests || rows.reduce((s: number, r: any) => s + (r.requests||0), 0),
        costCny: d.usage?.totals?.estimated_cost_cny || rows.reduce((s: number, r: any) => s + (r.estimated_cost_cny||r.cost_cny||0), 0),
        costUsd: d.usage?.totals?.estimated_cost_usd || rows.reduce((s: number, r: any) => s + (r.estimated_cost_usd||0), 0),
        balanceText,
        balanceStatus,
        pricingStatus: d.usage?.pricing_status || "ok",
        unpricedRows: Number(d.usage?.unpriced_rows || 0),
        unpricedReasons: d.usage?.unpriced_reasons || [],
      };

      const palettes = [
        ["rgba(6,95,107,0.85)", "rgba(6,182,212,0.85)", "rgba(6,182,212,0.28)"],
        ["rgba(61,21,120,0.85)", "rgba(124,58,237,0.85)", "rgba(124,58,237,0.28)"],
        ["rgba(3,105,161,0.85)", "rgba(56,189,248,0.85)", "rgba(56,189,248,0.28)"],
        ["rgba(21,128,61,0.85)", "rgba(34,197,94,0.85)", "rgba(34,197,94,0.28)"],
      ];
      const layers = ["input_cache_miss", "output_tokens", "input_cache_hit"];

      for (let si = 0; si < llmChartSeries.value.length; si++) {
        const series = llmChartSeries.value[si];
        const colors = palettes[si % palettes.length];
        const canvas = llmModelRefs.value[series.key];
        if (!canvas) continue;
        const ctx = canvas.getContext("2d");
        if (!ctx) continue;
        const dpr = 2;
        const W = canvas.offsetWidth || 320, H = canvas.offsetHeight || 112;
        canvas.width = W * dpr; canvas.height = H * dpr;
        ctx.scale(dpr, dpr); ctx.clearRect(0, 0, W, H);

        const modelRows = rows.filter((r: any) => chartKey(r) === series.key);
        const modelHasUsage = modelRows.some((r: any) => tokenTotal(r) > 0);
        if (!modelHasUsage) {
          ctx.fillStyle = "#475569";
          ctx.font = "10px monospace";
          ctx.textAlign = "center";
          ctx.fillText(t("activity.noProjectCalls"), W / 2, H / 2);
          ctx.textAlign = "start";
          continue;
        }
        const maxVal = Math.max(...modelRows.map((r: any) => tokenTotal(r)), 1);
        const leftPad = 34, botPad = 16;
        const chartH = H - 6 - botPad;
        const slotW = (W - leftPad - 2) / dates.length;
        const barW = Math.max(2, Math.min(16, slotW * 0.38));

        ctx.fillStyle = "#64748b"; ctx.font = "8px monospace";
        for (let t = 0; t <= maxVal; t += maxVal / 3) {
          const y = H - botPad - (t / maxVal) * chartH;
          ctx.fillText(t>=1e6?(t/1e6).toFixed(0)+"M":t>=1e3?(t/1e3).toFixed(0)+"K":String(t), 2, y+3);
          ctx.strokeStyle = "rgba(148,163,184,0.05)"; ctx.lineWidth = 0.5;
          ctx.beginPath(); ctx.moveTo(leftPad, y); ctx.lineTo(W-2, y); ctx.stroke();
        }
        dates.forEach((date, di) => {
          const row = rowByDate[date + "|" + series.key];
          if (!row) return;
          const x0 = leftPad + di * slotW + (slotW - barW) / 2;
          let yBottom = H - botPad;
          layers.forEach((layer, li) => {
            const val = row[layer] || 0;
            const h = (val / maxVal) * chartH;
            ctx.fillStyle = colors[li];
            ctx.fillRect(x0, yBottom - h, barW, h);
            yBottom -= h;
          });
          const labelEvery = Math.max(1, Math.ceil(dates.length / 8));
          if (di % labelEvery === 0) { ctx.fillStyle = "#64748b"; ctx.font = "7px monospace"; ctx.fillText(date.slice(5), x0, H-3); }
        });
      }

      // Cost chart
      const costCanvas = llmCostRef.value;
      if (costCanvas) {
        const ctx = costCanvas.getContext("2d");
        if (ctx) {
          const dpr = 2;
          const W = costCanvas.offsetWidth || 320, H = costCanvas.offsetHeight || 82;
          costCanvas.width = W * dpr; costCanvas.height = H * dpr;
          ctx.scale(dpr, dpr); ctx.clearRect(0, 0, W, H);
          const costByDate: Record<string, number> = {};
          for (const r of rows) {
            const date = String(r.utc_date || "").slice(0, 10);
            if (!date) continue;
            costByDate[date] = (costByDate[date] || 0) + Number(r.estimated_cost_cny || r.cost_cny || 0);
          }
          const costs = Object.values(costByDate).filter(cost => cost > 0);
          const maxCost = Math.max(...costs, 1);
          const leftPad = 34, botPad = 14, chartH = H - 8 - botPad;
          const slotWc = (W - leftPad - 2) / dates.length;
          const barWc = Math.max(2, Math.min(16, slotWc * 0.38));
          ctx.fillStyle = "#64748b"; ctx.font = "8px monospace";
          const fmtCostTick = (v: number) => {
            if (maxCost >= 100) return "¥" + v.toFixed(0);
            if (maxCost >= 1) return "¥" + v.toFixed(2);
            return "¥" + v.toFixed(3);
          };
          for (let t = 0; t <= maxCost; t += maxCost / 3) {
            const y = H - botPad - (t / maxCost) * chartH;
            ctx.fillText(fmtCostTick(t), 2, y+3);
            ctx.strokeStyle = "rgba(148,163,184,0.05)"; ctx.lineWidth = 0.5;
            ctx.beginPath(); ctx.moveTo(leftPad, y); ctx.lineTo(W-2, y); ctx.stroke();
          }
          const costDates = dates.filter(d => costByDate[d] > 0);
          if (costDates.length > 0) {
            for (const date of costDates) {
              const di = dates.indexOf(date), val = costByDate[date];
              const x0 = leftPad + di * slotWc + (slotWc - barWc) / 2;
              ctx.fillStyle = "rgba(232,168,64,0.42)";
              ctx.fillRect(x0, H - botPad - (val/maxCost)*chartH, barWc, (val/maxCost)*chartH);
            }
            ctx.beginPath(); ctx.strokeStyle = "#e8a840"; ctx.lineWidth = 1.2;
            for (let i = 0; i < costDates.length; i++) {
              const di = dates.indexOf(costDates[i]), val = costByDate[costDates[i]];
              const x = leftPad + di * slotWc + slotWc / 2;
              const y = H - botPad - (val/maxCost)*chartH;
              if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.stroke();
          }
          const labelEvery = Math.max(1, Math.ceil(dates.length / 8));
          dates.forEach((date, di) => {
            if (di % labelEvery === 0) { ctx.fillStyle = "#64748b"; ctx.font = "7px monospace"; ctx.fillText(date.slice(5), leftPad + di*slotWc, H-2); }
          });
        }
      }
    } catch (e) { /* silent */ }
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
    llmCostRef,
    llmHasUsage,
    llmChartSeries,
    llmTotals,
    setLlmModelCanvas,
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
    fmtNum,
    fmtMoney,
    fmtGb,
    fmtPercent,
    pctWidth,
    fetchData,
    fetchSlowData,
    drawCharts,
    drawLlmUsageChart,
  };
}
