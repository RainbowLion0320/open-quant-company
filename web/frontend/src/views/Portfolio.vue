<template>
  <div class="view-page">
    <div class="flex items-center justify-between mb-2">
      <span class="text-2xs" style="color:var(--text-disabled)">{{ summary.total_asset ? '¥' + summary.total_asset.toLocaleString() : '—' }}</span>
      <div class="flex gap-2">
        <button class="btn btn-sm" @click="refresh" :disabled="loading">
          {{ loading ? '刷新中...' : '刷新状态' }}
        </button>
        <button class="btn btn-sm btn-primary" @click="loadAll" :disabled="loading">
          载入数据
        </button>
      </div>
    </div>

    <!-- Balance Cards -->
    <div class="grid grid-cols-2 lg:grid-cols-5 gap-3">
      <div class="glass-card metric-card">
        <div class="metric-label">总资产</div>
        <div class="metric-value primary">
          ¥{{ summary.total_asset?.toLocaleString() || '—' }}
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-label">可用现金</div>
        <div class="metric-value">
          ¥{{ summary.cash?.toLocaleString() || '—' }}
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-label">持仓市值</div>
        <div class="metric-value">
          ¥{{ summary.market_value?.toLocaleString() || '—' }}
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-label">总收益</div>
        <div class="metric-value" :style="{ color: summary.total_return_pct >= 0 ? 'var(--positive)' : 'var(--negative)' }">
          {{ fmtReturn(summary.total_return_pct) }}
        </div>
      </div>
      <div class="glass-card metric-card">
        <div class="metric-label">最高权益</div>
        <div class="metric-value">
          ¥{{ (summary.peak_equity || 0).toLocaleString() }}
        </div>
      </div>
    </div>

    <!-- NAV Equity Curve -->
    <div class="glass-card card-pad-lg">
      <div class="flex justify-between items-center mb-3">
        <div class="text-xs font-semibold tracking-wide" style="color:var(--text-secondary)">
          权益曲线 ({{ navData.length }} 天)
        </div>
      </div>
      <div ref="chartRef" style="height:280px"></div>
      <div v-if="!navData.length" class="text-xs text-center py-10" style="color:var(--text-disabled)">
        暂无数据 — 运行 python scripts/execute_paper_trades.py 生成 NAV
      </div>
    </div>

    <!-- Positions -->
    <div class="glass-card card-pad-lg">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">
        当前持仓 ({{ positions.length }})
      </div>
      <div v-if="positions.length" class="table-shell" style="--table-min:760px">
        <table class="data-table">
          <colgroup>
            <col style="width:13%">
            <col style="width:16%">
            <col style="width:8%">
            <col style="width:12%">
            <col style="width:12%">
            <col style="width:14%">
            <col style="width:13%">
            <col style="width:12%">
          </colgroup>
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th class="text-right">数量</th>
              <th class="text-right">成本</th>
              <th class="text-right">现价</th>
              <th class="text-right">市值</th>
              <th class="text-right">盈亏</th>
              <th class="text-right">比例</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in positions" :key="p.code">
              <td class="font-mono" style="color:var(--accent)">{{ p.code }}</td>
              <td>{{ p.name }}</td>
              <td class="text-right font-mono">{{ p.volume }}</td>
              <td class="text-right font-mono">¥{{ p.avg_cost?.toFixed(2) }}</td>
              <td class="text-right font-mono">¥{{ p.current_price?.toFixed(2) }}</td>
              <td class="text-right font-mono">¥{{ (p.market_value || 0).toLocaleString() }}</td>
              <td class="text-right font-mono" :style="{ color: (p.pnl||0) >= 0 ? 'var(--positive)' : 'var(--negative)' }">
                {{ fmtPnl(p.pnl) }}
              </td>
              <td class="text-right font-mono" :style="{ color: (p.pnl_pct||0) >= 0 ? 'var(--positive)' : 'var(--negative)' }">
                {{ (p.pnl_pct || 0).toFixed(1) }}%
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state empty-state-compact">暂无持仓</div>
    </div>

    <!-- Trade History -->
    <div class="glass-card card-pad-lg">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">
        交易记录 ({{ tradeTotal }} 笔)
      </div>
      <div v-if="trades.length" class="table-shell" style="--table-min:720px">
        <table class="data-table">
          <colgroup>
            <col style="width:16%">
            <col style="width:14%">
            <col style="width:10%">
            <col style="width:14%">
            <col style="width:10%">
            <col style="width:20%">
            <col style="width:16%">
          </colgroup>
          <thead>
            <tr>
              <th>日期</th>
              <th>代码</th>
              <th>方向</th>
              <th class="text-right">价格</th>
              <th class="text-right">数量</th>
              <th class="text-right">金额</th>
              <th>策略</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in trades" :key="t.code + t.date + t.side">
              <td class="font-mono text-[10px]">{{ t.date }}</td>
              <td class="font-mono" style="color:var(--accent)">{{ t.code }}</td>
              <td :style="{ color: t.side === 'buy' ? 'var(--positive)' : 'var(--negative)' }">
                {{ t.side === 'buy' ? '买入' : '卖出' }}
              </td>
              <td class="text-right font-mono">¥{{ t.price?.toFixed(2) }}</td>
              <td class="text-right font-mono">{{ t.volume }}</td>
              <td class="text-right font-mono">¥{{ (t.amount || 0).toLocaleString() }}</td>
              <td class="text-[10px]" style="color:var(--text-tertiary)">{{ t.strategy }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state empty-state-compact">暂无交易记录</div>
    </div>

    <!-- Order Form -->
    <div class="glass-card card-pad-lg">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">手动下单 (测试用)</div>
      <div class="flex flex-col md:flex-row gap-3 md:items-end">
        <div class="flex-1">
          <div class="text-[10px] mb-1" style="color:var(--text-disabled)">股票代码</div>
          <input v-model="order.symbol" type="text" placeholder="000001" class="w-full" />
        </div>
        <div class="w-full md:w-20">
          <div class="text-[10px] mb-1" style="color:var(--text-disabled)">方向</div>
          <select v-model="order.side" class="w-full">
            <option value="buy">买入</option>
            <option value="sell">卖出</option>
          </select>
        </div>
        <div class="w-full md:w-24">
          <div class="text-[10px] mb-1" style="color:var(--text-disabled)">数量</div>
          <input v-model.number="order.shares" type="number" min="100" step="100" class="w-full" />
        </div>
        <button @click="submitOrder" class="btn btn-primary">提交</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, nextTick, watch } from "vue";
import * as echarts from "echarts";

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
const navData = ref<NavPoint[]>([]);
const trades = ref<Trade[]>([]);
const tradeTotal = ref(0);
const summary = ref<Summary>({
  total_asset: 0, cash: 0, market_value: 0, total_return: 0,
  total_return_pct: 0, positions_count: 0, peak_equity: 0, nav_days: 0,
});
const loading = ref(false);
const order = reactive({ symbol: "", side: "buy" as "buy" | "sell", shares: 100 });
const chartRef = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

function fmtPnl(v: number | undefined) {
  if (v == null) return "—";
  const sign = v > 0 ? "+" : v < 0 ? "-" : "";
  return sign + "¥" + Math.abs(v).toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}
function fmtReturn(v: number | undefined) {
  if (v == null || v === 0) return "0.00%";
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%";
}

async function loadAll() {
  loading.value = true;
  try {
    const [posRes, navRes, tradeRes, sumRes] = await Promise.all([
      fetch("/api/portfolio/positions").then(r => r.json()),
      fetch("/api/portfolio/nav").then(r => r.json()),
      fetch("/api/portfolio/trades?limit=50").then(r => r.json()),
      fetch("/api/portfolio/summary").then(r => r.json()),
    ]);

    positions.value = (posRes.positions || []).map((p: any) => ({
      code: p.code, name: p.name, volume: p.volume,
      avg_cost: p.avg_cost, current_price: p.current_price,
      market_value: p.market_value, pnl: p.pnl, pnl_pct: p.pnl_pct,
    }));

    navData.value = navRes.nav || [];
    trades.value = tradeRes.trades || [];
    tradeTotal.value = tradeRes.total || 0;

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
  } catch (e) {
    console.error("Load portfolio failed:", e);
  } finally {
    loading.value = false;
  }
}

async function refresh() {
  loading.value = true;
  try {
    await fetch("/api/portfolio/refresh", { method: "POST" });
    await loadAll();
  } finally {
    loading.value = false;
  }
}

async function submitOrder() {
  if (!order.symbol) return;
  try {
    await fetch("/api/portfolio/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: order.symbol, side: order.side, volume: order.shares, price: 0 }),
    });
    order.symbol = "";
    order.shares = 100;
    await loadAll();
  } catch (e) {
    console.error("Order failed:", e);
  }
}

function renderChart() {
  if (!chartRef.value || !navData.value.length) return;

  if (!chart) {
    chart = echarts.init(chartRef.value);
  }

  const dates = navData.value.map(d => d.date);
  const assets = navData.value.map(d => d.total_asset);

  chart.setOption({
    grid: { top: 8, right: 16, bottom: 24, left: 60 },
    xAxis: { type: "category", data: dates, axisLine: { lineStyle: { color: "rgba(148,163,184,0.15)" } },
      axisLabel: { color: "#64748b", fontSize: 9, interval: Math.max(1, Math.floor(dates.length / 8)) } },
    yAxis: { type: "value", axisLabel: { color: "#64748b", fontSize: 9, formatter: (v: number) => (v / 10000).toFixed(0) + "万" },
      splitLine: { lineStyle: { color: "rgba(148,163,184,0.06)" } } },
    series: [{
      type: "line", data: assets, showSymbol: false, smooth: true,
      sampling: false,
      lineStyle: { color: "#00d4ff", width: 1.5 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: "rgba(0,212,255,0.12)" },
        { offset: 1, color: "rgba(0,212,255,0.01)" },
      ]) },
      markLine: { silent: true, symbol: "none", lineStyle: { color: "rgba(255,255,255,0.15)", type: "dashed", width: 1 },
        data: [{ yAxis: 1_000_000, label: { formatter: "本金", color: "#64748b", fontSize: 9 } }] },
    }],
  }, true);
}

watch(navData, () => nextTick(renderChart));

onMounted(loadAll);
onUnmounted(() => { chart?.dispose(); });
</script>
