<template>
  <div class="p-6 space-y-5">
    <!-- Header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">市场总览</h1>
        <p class="page-subtitle">实时市场状态 · 参数调优 · 策略监控</p>
      </div>
      <button @click="refresh" class="btn btn-sm">⟳ 刷新</button>
    </div>

    <!-- Regime Status Cards -->
    <div class="grid grid-cols-4 gap-3">
      <div class="glass-card glow-cyan" style="padding:14px 16px">
        <div class="text-[10px] tracking-wider uppercase" style="color:var(--text-tertiary)">市场状态</div>
        <div class="text-xl font-semibold mt-1" :style="{ color: regimeColor }">{{ regimeLabel }}</div>
        <div class="mt-2 h-1 rounded-full" style="background:var(--border-subtle)">
          <div class="h-full rounded-full transition-all duration-500" :style="{ width: regimeWidth, background: regimeBarColor }"></div>
        </div>
      </div>
      <div class="glass-card" style="padding:14px 16px">
        <div class="text-[10px] tracking-wider uppercase" style="color:var(--text-tertiary)">均线排列</div>
        <div class="text-sm font-semibold mt-1" style="color:var(--text-secondary)">{{ store.regime?.ma_trend || '—' }}</div>
        <div class="text-[10px] mt-1" style="color:var(--text-disabled)">MA5 / MA20 / MA60</div>
      </div>
      <div class="glass-card" style="padding:14px 16px">
        <div class="text-[10px] tracking-wider uppercase" style="color:var(--text-tertiary)">成交量趋势</div>
        <div class="text-sm font-semibold mt-1" style="color:var(--text-secondary)">{{ store.regime?.volume_trend || '—' }}</div>
        <div class="text-[10px] mt-1" style="color:var(--text-disabled)">20日均量对比</div>
      </div>
      <div class="glass-card glow-quantum" style="padding:14px 16px">
        <div class="text-[10px] tracking-wider uppercase" style="color:var(--text-tertiary)">市场宽度</div>
        <div class="text-xl font-semibold font-mono mt-1" style="color:var(--quantum-glow)">
          {{ store.regime?.breadth?.toFixed(2) || '—' }}
        </div>
      </div>
    </div>

    <!-- K-line Chart -->
    <div class="glass-card" style="padding:20px">
      <div class="flex items-center justify-between mb-4">
        <div class="text-xs font-semibold tracking-wide" style="color:var(--text-secondary)">上证指数 K 线</div>
        <span class="text-[10px]" style="color:var(--text-disabled)">日线</span>
      </div>
      <div ref="chartRef" style="height:360px"></div>
    </div>

    <!-- Strategy Cards -->
    <div v-if="registry.length" class="grid gap-4" :style="{ gridTemplateColumns: `repeat(${Math.min(registry.length, 4)}, 1fr)` }">
      <div v-for="s in registry" :key="s.name" class="glass-card glow-cyan" style="padding:18px">
        <!-- Strategy Header -->
        <div class="flex items-center gap-2 mb-4">
          <div class="w-2 h-2 rounded-full" :style="{ background: s.color, boxShadow: `0 0 6px ${s.color}` }"></div>
          <div class="text-xs font-semibold tracking-wide" :style="{ color: s.color }">{{ s.label }}</div>
        </div>

        <!-- Buffett Params -->
        <template v-if="s.name === 'buffett'">
          <SliderGroup label="ROE ≥" :val="fmtPct(edit.buffett_roe)" :model="edit.buffett_roe" @u="v=>edit.buffett_roe=v" :min="5" :max="30" color="var(--accent)" />
          <SliderGroup label="毛利率 ≥" :val="fmtPct(edit.buffett_gm)" :model="edit.buffett_gm" @u="v=>edit.buffett_gm=v" :min="5" :max="50" color="var(--accent)" />
          <SliderGroup label="D/E ≤" :val="edit.buffett_de.toFixed(1)" :model="edit.buffett_de" @u="v=>edit.buffett_de=v" :min="0.5" :max="3" :step="0.1" color="var(--accent)" />
          <div class="mt-4 pt-3 border-t" style="border-color:var(--border-subtle)">
            <div class="text-[10px] tracking-wider mb-3" style="color:var(--text-disabled)">DCF 估值参数</div>
            <SliderGroup label="折现率" :val="fmtPct(edit.dcf_discount)" :model="edit.dcf_discount" @u="v=>edit.dcf_discount=v" :min="5" :max="15" />
            <SliderGroup label="永续增长" :val="fmtPct(edit.dcf_terminal)" :model="edit.dcf_terminal" @u="v=>edit.dcf_terminal=v" :min="1" :max="5" />
            <SliderGroup label="安全边际 ≥" :val="fmtPct(edit.dcf_margin)" :model="edit.dcf_margin" @u="v=>edit.dcf_margin=v" :min="10" :max="50" :step="5" />
          </div>
        </template>

        <!-- Multifactor Params -->
        <template v-if="s.name === 'multifactor'">
          <SliderGroup label="质量" :val="fmtPct(edit.mf_quality)" :model="edit.mf_quality" @u="v=>edit.mf_quality=v" :min="10" :max="60" :step="5" color="var(--positive)" />
          <SliderGroup label="估值" :val="fmtPct(edit.mf_valuation)" :model="edit.mf_valuation" @u="v=>edit.mf_valuation=v" :min="10" :max="60" :step="5" color="var(--positive)" />
          <SliderGroup label="技术" :val="fmtPct(edit.mf_technical)" :model="edit.mf_technical" @u="v=>edit.mf_technical=v" :min="5" :max="30" :step="5" color="var(--positive)" />
          <SliderGroup label="市场" :val="fmtPct(edit.mf_market)" :model="edit.mf_market" @u="v=>edit.mf_market=v" :min="5" :max="30" :step="5" color="var(--positive)" />
          <div class="mt-4 pt-3 border-t" style="border-color:var(--border-subtle)">
            <SliderGroup label="买入阈值" :val="edit.mf_threshold.toString()" :model="edit.mf_threshold" @u="v=>edit.mf_threshold=v" :min="30" :max="75" :step="5" color="var(--positive)" />
          </div>
        </template>

        <!-- Cybernetic Params -->
        <template v-if="s.name === 'cybernetic'">
          <div class="pb-3 mb-3 border-b" style="border-color:var(--border-subtle)">
            <div class="text-[10px] tracking-wider mb-2" style="color:var(--positive)">◉ 牛市</div>
            <SliderGroup label="仓位" :val="fmtPct(edit.cy_bull_pos)" :model="edit.cy_bull_pos" @u="v=>edit.cy_bull_pos=v" :min="10" :max="50" :step="5" color="var(--positive)" />
            <SliderGroup label="止损" :val="fmtPct(-edit.cy_bull_stop)" :model="edit.cy_bull_stop" @u="v=>edit.cy_bull_stop=v" :min="-15" :max="-3" color="var(--positive)" />
          </div>
          <div class="pb-3 mb-3 border-b" style="border-color:var(--border-subtle)">
            <div class="text-[10px] tracking-wider mb-2" style="color:var(--warning)">◉ 震荡</div>
            <SliderGroup label="仓位" :val="fmtPct(edit.cy_side_pos)" :model="edit.cy_side_pos" @u="v=>edit.cy_side_pos=v" :min="5" :max="30" :step="5" color="var(--warning)" />
          </div>
          <div>
            <div class="text-[10px] tracking-wider mb-2" style="color:var(--negative)">◉ 熊市</div>
            <SliderGroup label="仓位" :val="fmtPct(edit.cy_bear_pos)" :model="edit.cy_bear_pos" @u="v=>edit.cy_bear_pos=v" :min="1" :max="15" color="var(--negative)" />
          </div>
        </template>

        <!-- ML Strategy -->
        <template v-if="s.name === 'ml_lgbm'">
          <div class="text-xs py-2" style="color:var(--text-disabled)">
            LightGBM 模型自动调参。参数在模型训练阶段由 Optuna 搜索。
          </div>
        </template>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="flex justify-end gap-2 pt-2">
      <button @click="resetParams" class="btn btn-ghost btn-sm">重置</button>
      <button @click="saveParams" class="btn btn-primary btn-sm">保存并重跑</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, reactive, watch } from "vue";
import { useMarketStore } from "../stores";
import { useECharts, QUANTUM_THEME } from "../charts/useECharts";
import SliderGroup from "../components/SliderGroup.vue";
import { api } from "../api";

const store = useMarketStore();

// ── ECharts ──
const chartRef = ref<HTMLElement | null>(null);
const { init: initChart, setOption } = useECharts(chartRef);

function renderChart() {
  if (!store.kline.length) return;
  initChart();

  const dates = store.kline.map((k: any) => k.date);
  const ohlc = store.kline.map((k: any) => [k.open, k.close, k.low, k.high]);
  const volumes = store.kline.map((k: any) => k.volume);

  setOption({
    ...QUANTUM_THEME,
    grid: [
      { left: 8, right: 8, top: 8, height: "68%" },
      { left: 8, right: 8, top: "80%", height: "14%" },
    ],
    xAxis: [
      { type: "category", data: dates, gridIndex: 0, axisLabel: { show: false } },
      { type: "category", data: dates, gridIndex: 1, axisLabel: { color: "#475569", fontSize: 9 } },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, scale: true, axisLabel: { color: "#64748b", fontSize: 9 }, splitLine: { lineStyle: { color: "rgba(255,255,255,0.03)" } } },
      { type: "value", gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    series: [
      {
        type: "candlestick", data: ohlc,
        itemStyle: { color: "#22c55e", color0: "#ef4444", borderColor: "#22c55e", borderColor0: "#ef4444" },
      },
      {
        type: "bar", data: volumes, xAxisIndex: 1, yAxisIndex: 1,
        itemStyle: { color: "rgba(0,212,255,0.15)" },
      },
    ],
  });
}

watch(() => store.kline, renderChart);

// ── Regime UI ──
const regimeLabel = computed(() => {
  const r = store.regime?.value; if (r === "bull") return "牛市"; if (r === "bear") return "熊市"; return "震荡";
});
const regimeColor = computed(() => {
  const r = store.regime?.value; if (r === "bull") return "var(--positive)"; if (r === "bear") return "var(--negative)"; return "var(--warning)";
});
const regimeBarColor = computed(() => {
  const r = store.regime?.value; if (r === "bull") return "var(--positive)"; if (r === "bear") return "var(--negative)"; return "var(--warning)";
});
const regimeWidth = computed(() => {
  const r = store.regime?.value; if (r === "bull") return "85%"; if (r === "bear") return "25%"; return "55%";
});

// ── Params ──
const registry = computed(() => store.registry || []);
const edit = reactive({
  buffett_roe: 15, buffett_gm: 30, buffett_de: 1.5,
  dcf_discount: 8, dcf_terminal: 3, dcf_margin: 30,
  mf_quality: 40, mf_valuation: 30, mf_technical: 15, mf_market: 15, mf_threshold: 45,
  cy_bull_pos: 30, cy_bull_stop: -8, cy_side_pos: 15, cy_bear_pos: 5,
});

function fmtPct(v: number) { return v.toFixed(0) + "%"; }

function loadFromConfig() {
  const c = store.config; if (!c.buffett) return;
  const b = c.buffett?.moat || {};
  const d = c.buffett?.margin_of_safety || {};
  edit.buffett_roe = (b.min_roe || 0.15) * 100;
  edit.buffett_gm = (b.min_gross_margin || 0.30) * 100;
  edit.buffett_de = b.max_debt_equity || 1.5;
  edit.dcf_discount = (d.dcf_discount_rate || 0.08) * 100;
  edit.dcf_terminal = (d.growth_rate_terminal || 0.03) * 100;
  edit.dcf_margin = (d.safety_margin_pct || 0.30) * 100;
  const m = c.signals?.multifactor || {}; const w = m.weights || {};
  edit.mf_quality = (w.quality || 0.40) * 100;
  edit.mf_valuation = (w.valuation || 0.30) * 100;
  edit.mf_technical = (w.technical || 0.15) * 100;
  edit.mf_market = (w.market || 0.15) * 100;
  const cy = c.cybernetics?.adaptive || {};
  edit.cy_bull_pos = (cy.bull?.position_size || 0.30) * 100;
  edit.cy_bull_stop = (cy.bull?.stop_loss || -0.08) * 100;
  edit.cy_side_pos = (cy.sideways?.position_size || 0.15) * 100;
  edit.cy_bear_pos = (cy.bear?.position_size || 0.05) * 100;
}

async function saveParams() {
  try {
    const d = await api.settings();
    d.buffett = d.buffett || {}; d.buffett.moat = d.buffett.moat || {};
    d.buffett.moat.min_roe = edit.buffett_roe / 100;
    d.buffett.moat.min_gross_margin = edit.buffett_gm / 100;
    d.buffett.moat.max_debt_equity = edit.buffett_de;
    d.buffett.margin_of_safety = d.buffett.margin_of_safety || {};
    d.buffett.margin_of_safety.dcf_discount_rate = edit.dcf_discount / 100;
    d.buffett.margin_of_safety.growth_rate_terminal = edit.dcf_terminal / 100;
    d.buffett.margin_of_safety.safety_margin_pct = edit.dcf_margin / 100;
    d.signals = d.signals || {}; d.signals.multifactor = d.signals.multifactor || {};
    d.signals.multifactor.weights = d.signals.multifactor.weights || {};
    d.signals.multifactor.weights.quality = edit.mf_quality / 100;
    d.signals.multifactor.weights.valuation = edit.mf_valuation / 100;
    d.signals.multifactor.weights.technical = edit.mf_technical / 100;
    d.signals.multifactor.weights.market = edit.mf_market / 100;
    d.cybernetics = d.cybernetics || {}; d.cybernetics.adaptive = d.cybernetics.adaptive || {};
    d.cybernetics.adaptive.bull = d.cybernetics.adaptive.bull || {};
    d.cybernetics.adaptive.bull.position_size = edit.cy_bull_pos / 100;
    d.cybernetics.adaptive.bull.stop_loss = edit.cy_bull_stop / 100;
    d.cybernetics.adaptive.sideways = d.cybernetics.adaptive.sideways || {};
    d.cybernetics.adaptive.sideways.position_size = edit.cy_side_pos / 100;
    d.cybernetics.adaptive.bear = d.cybernetics.adaptive.bear || {};
    d.cybernetics.adaptive.bear.position_size = edit.cy_bear_pos / 100;
    await api.saveSettings(d);
    await store.fetchMarket(); loadFromConfig();
  } catch {}
}
function resetParams() { loadFromConfig(); }

async function refresh() { await store.fetchMarket(); renderChart(); }

watch(() => store.config, loadFromConfig, { immediate: true });

onMounted(async () => {
  await store.fetchMarket();
  initChart();
  renderChart();
  loadFromConfig();
});
</script>
