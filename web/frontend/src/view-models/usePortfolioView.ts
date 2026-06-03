import { ref, reactive, onMounted, onUnmounted, nextTick, watch } from "vue";
import { api } from "../api";
import { getECharts } from "../charts/useECharts";
import { useI18n } from "../i18n";
import { fmtSignedPercentValue } from "../utils/format";

export function usePortfolioView() {

  interface Position {
    code: string; name: string; volume: number; avg_cost: number;
    current_price: number; market_value: number; pnl: number; pnl_pct: number;
  }
  interface NavPoint { date: string; total_asset: number; cash: number; market_value: number; }
  interface Trade {
    date: string; code: string; name: string; side: string;
    price: number; volume: number; amount: number; strategy: string;
  }
  interface Summary {
    total_asset: number; cash: number; market_value: number;
    total_return: number; total_return_pct: number;
    positions_count: number; peak_equity: number; nav_days: number;
  }

  const positions = ref<Position[]>([]);
  const { currentLocale, t } = useI18n();
  const translate = t;
  const navData = ref<NavPoint[]>([]);
  const trades = ref<Trade[]>([]);
  const tradeTotal = ref(0);
  const sectorExposure = ref<{ sector: string; weight: number; market_value: number; position_count: number }[]>([]);
  const error = ref("");
  const summary = ref<Summary>({
    total_asset: 0, cash: 0, market_value: 0, total_return: 0,
    total_return_pct: 0, positions_count: 0, peak_equity: 0, nav_days: 0,
  });
  const loading = ref(false);
  const order = reactive({ symbol: "", side: "buy" as "buy" | "sell", shares: 100 });
  const chartRef = ref<HTMLElement | null>(null);
  let chart: any = null;

  function fmtPnl(v: number | undefined) {
    if (v == null) return "—";
    const sign = v > 0 ? "+" : v < 0 ? "-" : "";
    return sign + "¥" + Math.abs(v).toLocaleString(currentLocale.value, { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }
  function fmtReturn(v: number | undefined) {
    if (v == null || v === 0) return "0.00%";
    return fmtSignedPercentValue(v);
  }
  async function loadAll() {
    loading.value = true;
    error.value = "";
    try {
      const [posRes, navRes, tradeRes, sumRes, expRes] = await Promise.all([
        api.portfolioPositionRows(),
        api.portfolioNav(),
        api.portfolioTrades(50),
        api.portfolioSummary(),
        api.sectorExposure(),
      ]);

      positions.value = (posRes.positions || []).map((p: any) => ({
        code: p.code, name: p.name, volume: p.volume,
        avg_cost: p.avg_cost, current_price: p.current_price,
        market_value: p.market_value, pnl: p.pnl, pnl_pct: p.pnl_pct,
      }));

      navData.value = navRes.nav || [];
      trades.value = tradeRes.trades || [];
      tradeTotal.value = tradeRes.total || 0;
      sectorExposure.value = expRes.exposure || [];

      const s = sumRes;
      summary.value = {
        total_asset: s.balance?.total_asset || 0,
        cash: s.balance?.cash || 0,
        market_value: s.position_value || 0,
        total_return: s.total_return || 0,
        total_return_pct: s.total_return_pct || 0,
        positions_count: s.positions_count || 0,
        peak_equity: s.peak_equity || 0,
        nav_days: s.nav_days || 0,
      };

      await nextTick();
      renderChart();
    } catch (e: any) {
      error.value = e?.message || translate("portfolio.loadError");
      console.error("Load portfolio failed:", e);
    } finally {
      loading.value = false;
    }
  }

  async function refresh() {
    loading.value = true;
    error.value = "";
    try {
      await api.portfolioRefresh();
      await loadAll();
    } catch (e: any) {
      error.value = e?.message || translate("portfolio.refreshError");
    } finally {
      loading.value = false;
    }
  }

  async function submitOrder() {
    if (!order.symbol) return;
    error.value = "";
    try {
      await api.portfolioOrder({ symbol: order.symbol, side: order.side, shares: order.shares });
      order.symbol = "";
      order.shares = 100;
      await loadAll();
    } catch (e: any) {
      error.value = e?.message || translate("portfolio.orderError");
      console.error("Order failed:", e);
    }
  }

  async function renderChart() {
    if (!chartRef.value || !navData.value.length) return;

    const ec = await getECharts();
    if (!chart) {
      chart = ec.init(chartRef.value);
    }

    const dates = navData.value.map(d => d.date);
    const assets = navData.value.map(d => d.total_asset);

    chart.setOption({
      grid: { top: 8, right: 16, bottom: 24, left: 60 },
      xAxis: { type: "category", data: dates, axisLine: { lineStyle: { color: "rgba(148,163,184,0.15)" } },
        axisLabel: { color: "#64748b", fontSize: 9, interval: Math.max(1, Math.floor(dates.length / 8)) } },
      yAxis: { type: "value", axisLabel: { color: "#64748b", fontSize: 9, formatter: (v: number) => currentLocale.value === "zh-CN" ? (v / 10000).toFixed(0) + "万" : (v / 1000).toFixed(0) + "k" },
        splitLine: { lineStyle: { color: "rgba(148,163,184,0.06)" } } },
      series: [{
        type: "line", data: assets, showSymbol: false, smooth: true,
        lineStyle: { color: "#00d4ff", width: 1.5 },
        areaStyle: { color: new ec.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: "rgba(0,212,255,0.12)" },
          { offset: 1, color: "rgba(0,212,255,0.01)" },
        ]) },
        markLine: { silent: true, symbol: "none", lineStyle: { color: "rgba(255,255,255,0.15)", type: "dashed", width: 1 },
          data: [{ yAxis: 1_000_000, label: { formatter: translate("portfolio.principal"), color: "#64748b", fontSize: 9 } }] },
      }],
    }, true);
  }

  watch(navData, () => nextTick(renderChart));
  watch(currentLocale, () => nextTick(renderChart));

  onMounted(loadAll);
  onUnmounted(() => { chart?.dispose(); });

  return {
    positions,
    currentLocale,
    t,
    translate,
    navData,
    trades,
    tradeTotal,
    sectorExposure,
    error,
    summary,
    loading,
    order,
    chartRef,
    fmtPnl,
    fmtReturn,
    loadAll,
    refresh,
    submitOrder,
    renderChart,
  };
}
