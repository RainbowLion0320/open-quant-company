<template>
  <div class="p-6 space-y-6">
    <!-- 搜索栏 -->
    <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
      <div class="flex gap-3">
        <input
          v-model="query"
          @keyup.enter="search"
          placeholder="输入股票代码 (如 600519)"
          class="flex-1 bg-white/5 border border-white/10 rounded px-4 py-3 text-sm font-mono focus:outline-none focus:border-[#7170ff]/50"
        />
        <button @click="search" class="px-8 py-3 text-sm rounded bg-[#7170ff] hover:bg-[#8b8aff] transition-colors">
          查询
        </button>
      </div>
    </div>

    <!-- 结果 -->
    <template v-if="stock">
      <!-- 基本信息 + 巴菲特评分 -->
      <div class="grid grid-cols-2 gap-4">
        <div class="bg-[#111214] border border-white/5 rounded-lg p-5">
          <h2 class="text-sm font-medium text-white/60 mb-4">{{ stock.basic?.name }} ({{ stock.basic?.symbol }})</h2>
          <dl class="space-y-2 text-sm">
            <div class="flex justify-between"><dt class="text-white/40">行业</dt><dd class="text-white/70">{{ stock.basic?.industry }}</dd></div>
            <div class="flex justify-between"><dt class="text-white/40">板块</dt><dd class="text-white/70">{{ stock.basic?.sector }}</dd></div>
          </dl>
        </div>

        <div v-if="stock.buffett_result" class="bg-[#111214] border border-white/5 rounded-lg p-5">
          <h2 class="text-sm font-medium text-white/60 mb-4">巴菲特价值评分</h2>
          <div class="text-3xl font-bold font-mono mb-3" :class="(stock.buffett_result.score || 0) >= 70 ? 'text-green-400' : 'text-white/70'">
            {{ stock.buffett_result.score?.toFixed(1) || '-' }}
          </div>
          <dl class="grid grid-cols-2 gap-2 text-xs">
            <div><span class="text-white/40">ROE (5y)</span><br><span class="text-white/70">{{ stock.buffett_result.avg_roe_5y?.toFixed(1) }}%</span></div>
            <div><span class="text-white/40">安全边际</span><br><span class="text-white/70">{{ stock.buffett_result.safety_margin_pct?.toFixed(1) }}%</span></div>
            <div><span class="text-white/40">毛利率</span><br><span class="text-white/70">{{ stock.buffett_result.avg_gross_margin_5y?.toFixed(1) || '-' }}%</span></div>
            <div><span class="text-white/40">D/E</span><br><span class="text-white/70">{{ stock.buffett_result.debt_equity_ratio?.toFixed(1) }}</span></div>
          </dl>
        </div>
      </div>

      <!-- K线 -->
      <div class="bg-[#111214] border border-white/5 rounded-lg p-5">
        <h2 class="text-sm font-medium text-white/60 mb-4">K线 (120日)</h2>
        <div ref="chartRef" style="height:320px"></div>
      </div>

      <!-- DCF计算器 -->
      <div class="bg-[#111214] border border-white/5 rounded-lg p-5">
        <h2 class="text-sm font-medium text-white/60 mb-4">DCF估值计算器</h2>
        <div class="grid grid-cols-2 gap-6">
          <div class="space-y-3">
            <div><label class="text-xs text-white/40">自由现金流 (亿)</label><input v-model.number="dcf.fcf" type="number" step="1" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm mt-1" /></div>
            <div><label class="text-xs text-white/40">增长率 (5年)</label><input v-model.number="dcf.growth" type="number" step="0.01" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm mt-1" /></div>
            <div><label class="text-xs text-white/40">永续增长率</label><input v-model.number="dcf.terminal" type="number" step="0.01" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm mt-1" /></div>
          </div>
          <div class="space-y-3">
            <div><label class="text-xs text-white/40">折现率</label><input v-model.number="dcf.discount" type="number" step="0.01" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm mt-1" /></div>
            <div><label class="text-xs text-white/40">总股本 (亿)</label><input v-model.number="dcf.shares" type="number" step="0.1" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm mt-1" /></div>
            <div><label class="text-xs text-white/40">当前价格</label><input v-model.number="dcf.price" type="number" step="0.01" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm mt-1" /></div>
          </div>
        </div>
        <div class="mt-4 p-3 bg-white/[0.02] rounded">
          <div class="text-xs text-white/40">内在价值: <span class="text-white/70 font-mono">¥{{ intrinsicValue.toFixed(2) }}</span></div>
          <div class="text-xs mt-1">安全边际: <span :class="safetyMargin >= 30 ? 'text-green-400' : safetyMargin >= 0 ? 'text-yellow-400' : 'text-red-400'" class="font-mono">{{ safetyMargin.toFixed(1) }}%</span></div>
        </div>
      </div>

      <!-- 策略信号 -->
      <div v-if="stock.signals?.length" class="bg-[#111214] border border-white/5 rounded-lg p-5">
        <h2 class="text-sm font-medium text-white/60 mb-4">策略信号</h2>
        <table class="w-full text-xs">
          <thead><tr class="text-white/40 border-b border-white/5"><th class="text-left py-2">策略</th><th class="text-right py-2">评分</th><th class="text-right py-2">信号</th></tr></thead>
          <tbody>
            <tr v-for="s in stock.signals" :key="s.symbol + s.strategy" class="border-b border-white/[0.02]">
              <td class="py-2">{{ s.strategy || s.name }}</td>
              <td class="py-2 text-right font-mono">{{ s.score?.toFixed(1) }}</td>
              <td class="py-2 text-right" :class="s.signal === 'buy' ? 'text-green-400' : 'text-white/30'">{{ s.signal === 'buy' ? '买入' : '持有' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <div v-else-if="!loading" class="text-center text-white/20 py-16">输入股票代码查询</div>
    <div v-else class="text-center text-white/20 py-16">加载中...</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue";
import { useRoute } from "vue-router";
import * as echarts from "echarts";

const route = useRoute();
const query = ref("");
const stock = ref<any>(null);
const loading = ref(false);
const chartRef = ref<HTMLDivElement>();
let chart: echarts.ECharts | null = null;

const dcf = ref({ fcf: 500, growth: 0.05, terminal: 0.03, discount: 0.08, shares: 12.5, price: 100 });

// 从 URL 自动触发查询
onMounted(() => {
  const code = route.params.code as string;
  if (code) {
    query.value = code;
    search();
  }
});

const intrinsicValue = computed(() => {
  const d = dcf.value;
  let total = 0;
  let f = d.fcf;
  for (let y = 1; y <= 5; y++) {
    f *= 1 + d.growth;
    total += f / Math.pow(1 + d.discount, y);
  }
  const terminal = (f * (1 + d.terminal)) / (d.discount - d.terminal);
  total += terminal / Math.pow(1 + d.discount, 5);
  return total / d.shares;
});

const safetyMargin = computed(() => {
  const d = dcf.value;
  if (d.price <= 0) return 0;
  return ((intrinsicValue.value - d.price) / intrinsicValue.value) * 100;
});

async function search() {
  if (!query.value.trim()) return;
  loading.value = true;
  try {
    const res = await fetch(`/api/stocks/${query.value.trim()}`);
    if (res.ok) {
      stock.value = await res.json();
      dcf.value.price = stock.value.buffett_result?.current_price || 100;
      await nextTick();
      initChart();
    } else {
      stock.value = null;
    }
  } catch {}
  loading.value = false;
}

function initChart() {
  if (!chartRef.value || !stock.value?.kline?.length) return;
  if (!chart) chart = echarts.init(chartRef.value, "dark");
  const dates = stock.value.kline.map((k: any) => k.date);
  chart.setOption({
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: dates, axisLabel: { show: false } },
    yAxis: { type: "value", scale: true },
    series: [{
      type: "candlestick",
      data: stock.value.kline.map((k: any) => [k.open, k.close, k.low, k.high]),
      itemStyle: { color: "#ef4444", color0: "#22c55e", borderColor: "#ef4444", borderColor0: "#22c55e" },
    }],
  });
}

onUnmounted(() => chart?.dispose());
</script>
