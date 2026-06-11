import { ref, computed, onMounted } from "vue";
import { api } from "../api";
import { useI18n } from "../i18n";
import { fmtPercentValue, fmtShortCount } from "../utils/format";

export function useDatabaseHealth() {

  interface HealthRow {
    table: string;
    source: string;
    label_zh: string;
    repairable: boolean;
    files: number;
    rows: number;
    columns: number;
    size_mb: number;
    missing_pct: number;
    missing_pct_10y: number;
    missing_pct_10y_plus: number;
    missing_cols: Record<string, number>;
    outlier_count: number;
    outlier_count_10y: number;
    outlier_count_10y_plus: number;
    outlier_cols: Record<string, number>;
    time_breakdown: Record<string, { rows: number; missing_pct: number; missing_cols: Record<string, number>; outliers: Record<string, number> }>;
    freshness_days: number | null;
    freshness_sla_days: number | null;
    freshness_status: "fresh" | "stale" | "missing" | "error" | "unknown" | "untracked" | string;
    error: string | null;
    checked_at: string;
  }

  interface HealthSummary {
    tables: number;
    total_size_mb: number;
    avg_missing_pct: number;
    total_outliers: number;
    checked_at: string;
  }

  const rows = ref<HealthRow[]>([]);
  const { currentLocale, t } = useI18n();
  const summary = ref<HealthSummary | null>(null);
  const status = ref<"loading" | "ok" | "no_data" | "error">("loading");
  const statusMessage = ref("");
  const expanded = ref<string | null>(null);
  const apiFallback = ref(false);
  const repairing = ref<Record<string, string>>({});  // table -> status

  const sortedRows = computed(() => {
    const arr = [...rows.value];
    arr.sort((a, b) => {
      const sa = (a.source || '').toLowerCase();
      const sb = (b.source || '').toLowerCase();
      if (sa !== sb) return sa.localeCompare(sb, currentLocale.value);
      return (a.label_zh || a.table).localeCompare(b.label_zh || b.table, currentLocale.value);
    });
    return arr;
  });

  const statusClass = computed(() => `dot-${status.value}`);
  const statusText = computed(() => {
    if (status.value === "loading") return t("database.loading");
    if (status.value === "no_data") return statusMessage.value || t("database.noData");
    if (status.value === "error") return statusMessage.value || t("database.loadFailed");
    return t("database.complete");
  });

  const missingColor = computed(() => {
    const v = summary.value?.avg_missing_pct ?? 0;
    if (v < 3) return "var(--positive)";
    if (v < 10) return "var(--warning)";
    return "var(--negative)";
  });

  const outlierColor = computed(() => {
    const v = summary.value?.total_outliers ?? 0;
    if (v < 1000) return "var(--positive)";
    if (v < 10000) return "var(--warning)";
    return "var(--negative)";
  });

  function fmtSize(mb: number | undefined | null): string {
    if (mb == null) return "—";
    if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
    if (mb >= 1) return `${mb.toFixed(1)} MB`;
    return `${(mb * 1024).toFixed(0)} KB`;
  }

  function fmtPercent(v: number | undefined | null): string {
    return fmtPercentValue(v).replace("—%", "—");
  }

  function fmtCountOk(v: number | undefined | null): string {
    if (v == null) return "—";
    if (v === 0) return "OK";
    return fmtShortCount(v);
  }

  function fmtCount(v: number | undefined | null): string {
    return fmtShortCount(v);
  }

  function fmtTime(iso: string | undefined): string {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      const pad = (n: number) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch {
      return iso.slice(0, 16);
    }
  }

  function fmtMiss10y(row: HealthRow): string {
    const v = (row as any).missing_pct_10y;
    if (v == null) return "—";
    if (v === 0) return "OK";
    return v.toFixed(1) + "%";
  }
  function fmtMiss10yPlus(row: HealthRow): string {
    const v = (row as any).missing_pct_10y_plus;
    if (v == null) return "—";
    if (v === 0) return "OK";
    return v.toFixed(1) + "%";
  }

  function freshnessLabel(days: number | null): string {
    if (days == null) return "—";
    if (days < 0) return t("database.inDays", { days: Math.abs(days) });
    if (days === 0) return t("database.today");
    if (days <= 30) return t("database.daysAgo", { days });
    if (days <= 365) return t("database.monthsAgo", { months: Math.round(days / 30) });
    return t("database.yearsAgo", { years: Math.round(days / 365) });
  }

  function missingClass(pct: number | null | undefined): string {
    if (pct == null) return "";
    if (pct === 0) return "val-ok";
    if (pct < 5) return "val-warn";
    return "val-bad";
  }

  function okClass(v: number | null | undefined): string {
    if (v == null) return "";
    if (v === 0) return "val-ok";
    return "";
  }

  function outlierClass(cnt: number | null | undefined): string {
    if (cnt == null) return "";
    if (cnt === 0) return "val-ok";
    if (cnt < 100) return "val-warn";
    return "val-bad";
  }

  function freshnessClass(row: HealthRow): string {
    const status = row.freshness_status;
    if (status === "fresh") return "val-ok";
    if (status === "stale" || status === "missing" || status === "error") return "val-bad";
    if (status === "unknown" || status === "untracked") return "";
    const days = row.freshness_days;
    if (days == null) return "";
    if (days < 0) return "val-ok";
    if (days <= 1) return "val-ok";
    if (days <= 7) return "val-warn";
    return "val-bad";
  }

  function bdMissingClass(pct: number): string {
    if (pct === 0) return "bd-ok";
    if (pct < 5) return "bd-low";
    if (pct < 20) return "bd-mid";
    return "bd-high";
  }

  function hasDetail(row: HealthRow): boolean {
    return !!(
      (row.missing_cols && Object.keys(row.missing_cols).length) ||
      (row.outlier_cols && Object.keys(row.outlier_cols).length) ||
      (row.time_breakdown && Object.keys(row.time_breakdown).length) ||
      row.error
    );
  }

  function toggleDetail(table: string) {
    expanded.value = expanded.value === table ? null : table;
  }

  async function startRepair(table: string) {
    repairing.value[table] = 'running';
    try {
      const data = await api.dbHealthRepair(table);
      if (data.status !== 'started') {
        repairing.value[table] = 'failed';
        return;
      }
      // Poll for completion
      const jobId = data.job_id;
      if (!jobId) {
        repairing.value[table] = 'failed';
        return;
      }
      const poll = async () => {
        const sd = await api.dbHealthRepairStatus(jobId);
        if (sd.status === 'done') {
          repairing.value[table] = 'done';
          await fetchData();
          setTimeout(() => { delete repairing.value[table]; }, 3000);
        } else if (sd.status === 'failed') {
          repairing.value[table] = 'failed';
          setTimeout(() => { delete repairing.value[table]; }, 5000);
        } else if (sd.status === 'running' || sd.status === 'pending') {
          setTimeout(poll, 1000);
        } else {
          repairing.value[table] = 'failed';
        }
      };
      setTimeout(poll, 500);
    } catch {
      repairing.value[table] = 'failed';
      setTimeout(() => { delete repairing.value[table]; }, 5000);
    }
  }

  async function fetchData() {
    status.value = "loading";
    statusMessage.value = "";
    try {
      const data = await api.dbHealth();
      if (data.status === "no_data") {
        status.value = "no_data";
        statusMessage.value = data.message || "";
        rows.value = [];
        summary.value = null;
        return;
      }
      if (data.status === "error") {
        status.value = "error";
        statusMessage.value = data.message || t("database.readFailed");
        rows.value = [];
        summary.value = null;
        return;
      }
      apiFallback.value = !!data.api_fallback;
      rows.value = data.data || [];
      summary.value = data.summary || null;
      status.value = "ok";
    } catch (e: any) {
      status.value = "error";
      statusMessage.value = e?.message || t("database.requestFailed");
    }
  }

  onMounted(fetchData);

  return {
    rows,
    currentLocale,
    t,
    summary,
    status,
    statusMessage,
    expanded,
    apiFallback,
    repairing,
    sortedRows,
    statusClass,
    statusText,
    missingColor,
    outlierColor,
    fmtSize,
    fmtPercent,
    fmtCountOk,
    fmtCount,
    fmtTime,
    fmtMiss10y,
    fmtMiss10yPlus,
    freshnessLabel,
    missingClass,
    okClass,
    outlierClass,
    freshnessClass,
    bdMissingClass,
    hasDetail,
    toggleDetail,
    startRepair,
    fetchData,
  };
}
