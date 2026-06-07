import { ref, computed, onMounted } from "vue";
import { api } from "../api";
import type { StockDetail, StockListItem } from "../api";
import { useI18n } from "../i18n";
import { colorBySignedRatio, fmtFixedNumber, fmtPercentValue, fmtRatioPct, fmtShortCount, fmtSignedRatioPct } from "../utils/format";

export function useStocksView() {

  const { t } = useI18n();
  const query = ref("");
  const stock = ref<StockDetail | null>(null);
  const defaultRows = ref<StockListItem[]>([]);
  const searched = ref(false);
  const loading = ref(false);
  const listLoading = ref(false);
  const error = ref("");
  const listUpdated = ref("");
  const listTotal = ref(0);

  function fmtPct(v: number | undefined) { return fmtRatioPct(v, 1); }
  function fmtPrice(v: number | null | undefined) { return v == null ? "—" : v.toFixed(v >= 100 ? 2 : 3); }
  function fmtNumber(v: number | null | undefined, digits = 1) { return fmtFixedNumber(v, digits); }
  function colorPct(v: number | null | undefined) { return colorBySignedRatio(v ?? 0); }
  function scoreColor(v: number | null | undefined) {
    if (v == null) return "var(--text-disabled)";
    if (v >= 70) return "var(--positive)";
    if (v >= 50) return "var(--warning)";
    return "var(--text-secondary)";
  }

  const filteredRows = computed(() => {
    const q = query.value.trim().toLowerCase();
    if (!q) return defaultRows.value;
    return defaultRows.value.filter(row => (
      row.symbol.toLowerCase().includes(q)
      || row.name.toLowerCase().includes(q)
      || row.industry.toLowerCase().includes(q)
    ));
  });

  const buyCandidateCount = computed(() => defaultRows.value.filter(row => row.signal === "buy").length);
  const positiveRatio = computed(() => {
    const priced = defaultRows.value.filter(row => row.change_pct != null);
    if (!priced.length) return "—";
    return `${((priced.filter(row => (row.change_pct || 0) > 0).length / priced.length) * 100).toFixed(0)}%`;
  });
  const valueCandidateCount = computed(() => defaultRows.value.filter(row => (row.buffett_score || 0) >= 70).length);
  const latestKline = computed(() => {
    const kline = stock.value?.kline || [];
    return kline.length ? kline[kline.length - 1] : null;
  });
  const previousKline = computed(() => {
    const kline = stock.value?.kline || [];
    return kline.length > 1 ? kline[kline.length - 2] : null;
  });
  const latestFinancial = computed(() => {
    const financials = stock.value?.financials || [];
    return financials.length ? financials[financials.length - 1] : null;
  });
  const detailChange = computed(() => {
    const latest = latestKline.value;
    const previous = previousKline.value;
    if (!latest || !previous || !previous.close) return null;
    return latest.close / previous.close - 1;
  });
  const detailMetrics = computed(() => {
    const s = stock.value;
    if (!s) return [];
    const fin = latestFinancial.value;
    const latest = latestKline.value;
    const change = detailChange.value;
    return [
      { label: t("sectors.industry"), value: s.basic.industry || "—" },
      { label: t("stocks.metrics.latestClose"), value: fmtPrice(latest?.close) },
      { label: t("stocks.metrics.dailyChange"), value: fmtSignedRatioPct(change, 1), color: colorPct(change) },
      { label: t("stocks.metrics.volume"), value: latest?.volume == null ? "—" : fmtShortCount(latest.volume) },
      { label: "ROE", value: fmtPercentValue(fin?.roe, 1) },
      { label: t("stocks.grossMargin"), value: fmtPercentValue(fin?.gross_margin, 1) },
      { label: t("stocks.metrics.revenue"), value: fmtNumber(fin?.revenue, 1) },
      { label: t("stocks.metrics.netProfit"), value: fmtNumber(fin?.net_profit, 1) },
    ];
  });

  const marketBadge = computed(() => {
    const m = stock.value?.basic.market;
    if (m === "主板") return "badge-green";
    if (m === "创业板") return "badge-amber";
    if (m === "科创板") return "badge-red";
    return "";
  });

  async function search() {
    if (!query.value.trim()) {
      searched.value = false;
      stock.value = null;
      return;
    }
    searched.value = true;
    loading.value = true;
    error.value = "";
    try {
      stock.value = await api.stock(query.value.trim());
    } catch (e: any) {
      error.value = e?.message || t("stocks.searchError");
      stock.value = null;
    } finally {
      loading.value = false;
    }
  }

  async function openStock(symbol: string) {
    query.value = symbol;
    await search();
  }

  async function loadStockList() {
    listLoading.value = true;
    error.value = "";
    try {
      const data = await api.stockList();
      defaultRows.value = data.stocks || [];
      listTotal.value = data.total || defaultRows.value.length;
      listUpdated.value = data.updated_at || "";
    } catch (e: any) {
      error.value = e?.message || t("stocks.poolError");
      defaultRows.value = [];
      listTotal.value = 0;
    } finally {
      listLoading.value = false;
    }
  }

  onMounted(loadStockList);

  return {
    t,
    query,
    stock,
    defaultRows,
    searched,
    loading,
    listLoading,
    error,
    listUpdated,
    listTotal,
    fmtPct,
    fmtPrice,
    fmtNumber,
    colorPct,
    scoreColor,
    filteredRows,
    buyCandidateCount,
    positiveRatio,
    valueCandidateCount,
    latestKline,
    previousKline,
    latestFinancial,
    detailChange,
    detailMetrics,
    marketBadge,
    search,
    openStock,
    loadStockList,
  };
}
