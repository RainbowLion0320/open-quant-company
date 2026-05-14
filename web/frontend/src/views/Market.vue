<template>
  <div class="p-5 space-y-5">
    <!-- 顶栏 -->
    <div class="flex items-center justify-between">
      <h1 class="text-sm font-semibold tracking-wide" style="color:var(--text-primary)">市场总览</h1>
      <button @click="store.fetchMarket()"
        class="text-xs rounded-md px-3 py-1.5 transition-colors"
        style="color:var(--text-tertiary); background:var(--bg-hover); border:1px solid var(--border-subtle)">
        刷新
      </button>
    </div>

    <!-- Regime -->
    <div class="grid grid-cols-4 gap-3">
      <div class="card p-3.5">
        <div class="text-[11px] font-medium tracking-wide" style="color:var(--text-quaternary)">状态</div>
        <div class="text-lg font-semibold mt-1 tabular-nums" :class="regimeColor">{{ regimeLabel }}</div>
      </div>
      <div class="card p-3.5">
        <div class="text-[11px] font-medium tracking-wide" style="color:var(--text-quaternary)">均线</div>
        <div class="text-sm mt-1 tabular-nums" style="color:var(--text-secondary)">{{ store.regime?.ma_trend || '—' }}</div>
      </div>
      <div class="card p-3.5">
        <div class="text-[11px] font-medium tracking-wide" style="color:var(--text-quaternary)">成交量</div>
        <div class="text-sm mt-1 tabular-nums" style="color:var(--text-secondary)">{{ store.regime?.volume_trend || '—' }}</div>
      </div>
      <div class="card p-3.5">
        <div class="text-[11px] font-medium tracking-wide" style="color:var(--text-quaternary)">宽度</div>
        <div class="text-lg font-semibold mt-1 tabular-nums" style="color:var(--text-primary)">{{ store.regime?.breadth?.toFixed(2) || '—' }}</div>
      </div>
    </div>

    <!-- K线 -->
    <div class="card p-4">
      <div class="text-xs font-medium tracking-wide mb-3" style="color:var(--text-tertiary)">上证指数</div>
      <div ref="chartRef" style="height:340px"></div>
    </div>

    <!-- 策略卡片 — 动态 -->
    <div class="grid grid-cols-3 gap-3" v-if="registry.length">
      <div v-for="s in registry" :key="s.name" class="card p-4">
        <div class="text-xs font-semibold tracking-wide mb-4" :style="{ color: s.color || 'var(--accent)' }">{{ s.label }}</div>

        <template v-if="s.name === 'buffett'">
          <SliderGroup label="ROE ≥" :val="pct(edit.buffett_roe)" :model="edit.buffett_roe" @u="v=>edit.buffett_roe=v" :min="5" :max="30" color="var(--accent)" />
          <SliderGroup label="毛利率 ≥" :val="pct(edit.buffett_gm)" :model="edit.buffett_gm" @u="v=>edit.buffett_gm=v" :min="5" :max="50" color="var(--accent)" />
          <SliderGroup label="D/E ≤" :val="edit.buffett_de.toFixed(1)" :model="edit.buffett_de" @u="v=>edit.buffett_de=v" :min="0.5" :max="3" :step="0.1" color="var(--accent)" />
          <div class="pt-3 mt-3 border-t" style="border-color:var(--border-subtle)">
            <div class="text-[10px] tracking-wide mb-3" style="color:var(--text-quaternary)">DCF 参数</div>
            <SliderGroup label="折现率" :val="pct(edit.dcf_discount)" :model="edit.dcf_discount" @u="v=>edit.dcf_discount=v" :min="5" :max="15" color="var(--accent)" />
            <SliderGroup label="永续增长" :val="pct(edit.dcf_terminal)" :model="edit.dcf_terminal" @u="v=>edit.dcf_terminal=v" :min="1" :max="5" color="var(--accent)" />
            <SliderGroup label="安全边际 ≥" :val="pct(edit.dcf_margin)" :model="edit.dcf_margin" @u="v=>edit.dcf_margin=v" :min="10" :max="50" :step="5" color="var(--accent)" />
          </div>
        </template>

        <template v-if="s.name === 'multifactor'">
          <SliderGroup label="质量" :val="pct(edit.mf_quality)" :model="edit.mf_quality" @u="v=>edit.mf_quality=v" :min="10" :max="60" :step="5" color="var(--green)" />
          <SliderGroup label="估值" :val="pct(edit.mf_valuation)" :model="edit.mf_valuation" @u="v=>edit.mf_valuation=v" :min="10" :max="60" :step="5" color="var(--green)" />
          <SliderGroup label="技术" :val="pct(edit.mf_technical)" :model="edit.mf_technical" @u="v=>edit.mf_technical=v" :min="5" :max="30" :step="5" color="var(--green)" />
          <SliderGroup label="市场" :val="pct(edit.mf_market)" :model="edit.mf_market" @u="v=>edit.mf_market=v" :min="5" :max="30" :step="5" color="var(--green)" />
          <div class="pt-3 mt-3 border-t" style="border-color:var(--border-subtle)">
            <SliderGroup label="买入阈值" :val="edit.mf_threshold.toString()" :model="edit.mf_threshold" @u="v=>edit.mf_threshold=v" :min="30" :max="75" :step="5" color="var(--green)" />
          </div>
        </template>

        <template v-if="s.name === 'cybernetic'">
          <div class="pb-3 mb-3 border-b" style="border-color:var(--border-subtle)">
            <div class="text-[10px] tracking-wide mb-2" style="color:var(--green)">牛</div>
            <SliderGroup label="仓位" :val="pct(edit.cy_bull_pos)" :model="edit.cy_bull_pos" @u="v=>edit.cy_bull_pos=v" :min="10" :max="50" :step="5" color="var(--green)" />
            <SliderGroup label="止损" :val="pct(-edit.cy_bull_stop)" :model="edit.cy_bull_stop" @u="v=>edit.cy_bull_stop=v" :min="-15" :max="-3" color="var(--green)" />
          </div>
          <div class="pb-3 mb-3 border-b" style="border-color:var(--border-subtle)">
            <div class="text-[10px] tracking-wide mb-2" style="color:var(--yellow)">震</div>
            <SliderGroup label="仓位" :val="pct(edit.cy_side_pos)" :model="edit.cy_side_pos" @u="v=>edit.cy_side_pos=v" :min="5" :max="30" :step="5" color="var(--yellow)" />
          </div>
          <div>
            <div class="text-[10px] tracking-wide mb-2" style="color:var(--red)">熊</div>
            <SliderGroup label="仓位" :val="pct(edit.cy_bear_pos)" :model="edit.cy_bear_pos" @u="v=>edit.cy_bear_pos=v" :min="1" :max="15" color="var(--red)" />
          </div>
        </template>
      </div>
    </div>

    <div class="flex justify-end gap-2">
      <button @click="resetParams" class="btn btn-ghost text-xs">重置</button>
      <button @click="saveParams" class="btn btn-primary text-xs">保存并重跑</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, reactive, watch } from "vue";
import { useMarketStore } from "../stores";
import SliderGroup from "../components/SliderGroup.vue";
import * as echarts from "echarts";

const store = useMarketStore();
const chartRef = ref<HTMLDivElement>();
let chart: echarts.ECharts | null = null;

const registry = computed(() => store.registry || []);

const edit = reactive({
  buffett_roe: 15, buffett_gm: 30, buffett_de: 1.5,
  dcf_discount: 8, dcf_terminal: 3, dcf_margin: 30,
  mf_quality: 40, mf_valuation: 30, mf_technical: 15, mf_market: 15, mf_threshold: 45,
  cy_bull_pos: 30, cy_bull_stop: -8, cy_side_pos: 15, cy_bear_pos: 5,
});

const regimeLabel = computed(() => {
  const r = store.regime?.value; if (r === "bull") return "牛市"; if (r === "bear") return "熊市"; return "震荡";
});
const regimeColor = computed(() => {
  const r = store.regime?.value; if (r === "bull") return "color:#27a644"; if (r === "bear") return "color:#e5484d"; return "color:#eab308";
});

function pct(v: number) { return v.toFixed(0) + "%"; }

function loadFromConfig() {
  const c = store.config; if (!c.buffett) return;
  const b = c.buffett?.moat || {};
  const d = c.buffett?.margin_of_safety || {};
  edit.buffett_roe = (b.roe_min || 0.15) * 100;
  edit.buffett_gm = (b.gross_margin_min || 0.30) * 100;
  edit.buffett_de = b.debt_equity_max || 1.5;
  edit.dcf_discount = (d.dcf_discount_rate || 0.08) * 100;
  edit.dcf_terminal = (d.growth_rate_terminal || 0.03) * 100;
  edit.dcf_margin = (d.safety_margin_pct || 0.30) * 100;
  const m = c.multifactor || {}; const w = m.weights || {};
  edit.mf_quality = (w.quality || 0.40) * 100;
  edit.mf_valuation = (w.valuation || 0.30) * 100;
  edit.mf_technical = (w.technical || 0.15) * 100;
  edit.mf_market = (w.market || 0.15) * 100;
  const cy = c.cybernetics || {};
  edit.cy_bull_pos = (cy.bull?.position_size || 0.30) * 100;
  edit.cy_bull_stop = (cy.bull?.stop_loss || -0.08) * 100;
  edit.cy_side_pos = (cy.sideways?.position_size || 0.15) * 100;
  edit.cy_bear_pos = (cy.bear?.position_size || 0.05) * 100;
}

async function saveParams() {
  try {
    const res = await fetch("/api/settings"); const d = await res.json();
    d.buffett = d.buffett || {}; d.buffett.moat = d.buffett.moat || {};
    d.buffett.moat.roe_min = edit.buffett_roe / 100;
    d.buffett.moat.gross_margin_min = edit.buffett_gm / 100;
    d.buffett.moat.debt_equity_max = edit.buffett_de;
    d.buffett.margin_of_safety = d.buffett.margin_of_safety || {};
    d.buffett.margin_of_safety.dcf_discount_rate = edit.dcf_discount / 100;
    d.buffett.margin_of_safety.growth_rate_terminal = edit.dcf_terminal / 100;
    d.buffett.margin_of_safety.safety_margin_pct = edit.dcf_margin / 100;
    d.multifactor = d.multifactor || {}; d.multifactor.weights = d.multifactor.weights || {};
    d.multifactor.weights.quality = edit.mf_quality / 100;
    d.multifactor.weights.valuation = edit.mf_valuation / 100;
    d.multifactor.weights.technical = edit.mf_technical / 100;
    d.multifactor.weights.market = edit.mf_market / 100;
    d.cybernetics = d.cybernetics || {};
    d.cybernetics.bull = d.cybernetics.bull || {};
    d.cybernetics.bull.position_size = edit.cy_bull_pos / 100;
    d.cybernetics.bull.stop_loss = edit.cy_bull_stop / 100;
    d.cybernetics.sideways = d.cybernetics.sideways || {};
    d.cybernetics.sideways.position_size = edit.cy_side_pos / 100;
    d.cybernetics.bear = d.cybernetics.bear || {};
    d.cybernetics.bear.position_size = edit.cy_bear_pos / 100;
    await fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d) });
    await store.fetchMarket(); loadFromConfig();
  } catch(e) {}
}
function resetParams() { loadFromConfig(); }

function initChart() {
  if (!chartRef.value || !store.kline.length) return;
  if (!chart) chart = echarts.init(chartRef.value, "dark");
  const dates = store.kline.map((k: any) => k.date);
  chart.setOption({
    tooltip: { trigger: "axis" },
    grid: [{ left: 50, right: 20, top: 10, height: "65%" }, { left: 50, right: 20, top: "78%", height: "14%" }],
    xAxis: [{ type: "category", data: dates, gridIndex: 0, axisLabel: { show: false } }, { type: "category", data: dates, gridIndex: 1 }],
    yAxis: [{ type: "value", gridIndex: 0, scale: true }, { type: "value", gridIndex: 1 }],
    series: [
      { type: "candlestick", data: store.kline.map((k: any) => [k.open, k.close, k.low, k.high]), itemStyle: { color: "#e5484d", color0: "#27a644", borderColor: "#e5484d", borderColor0: "#27a644" } },
      { type: "bar", data: store.kline.map((k: any) => k.volume), xAxisIndex: 1, yAxisIndex: 1, itemStyle: { color: "rgba(113,112,255,0.3)" } },
    ],
  });
}

watch(() => store.kline, initChart);
watch(() => store.config, loadFromConfig, { immediate: true });
onMounted(async () => { await store.fetchMarket(); initChart(); loadFromConfig(); });
onUnmounted(() => chart?.dispose());
</script>
