<template>
  <div class="app-shell">
    <div class="orbital-grid"></div>
    <div class="scanline"></div>

    <aside class="nav-rail">
      <router-link to="/" class="brand-mark" aria-label="Quant Agent">
        <span class="brand-core">QA</span>
        <span class="brand-ring"></span>
      </router-link>

      <nav class="nav-stack" aria-label="主导航">
        <router-link
          v-for="item in nav"
          :key="item.path"
          :to="item.path"
          class="nav-node"
          :class="{ active: isActive(item.path) }"
          @mouseenter="hovered = item.label"
          @mouseleave="hovered = ''"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path :d="item.pathData" />
          </svg>
          <span class="nav-tooltip">{{ item.label }}</span>
        </router-link>
      </nav>

      <div class="core-status">
        <span>CORE</span>
        <strong>{{ coreVersion }}</strong>
      </div>
    </aside>

    <section class="workspace">
      <header class="command-bar">
        <div class="system-title">
          <span class="system-kicker">HERMES QUANT AGENT</span>
          <strong>{{ routeTitle }}</strong>
        </div>
        <div class="telemetry-strip">
          <div class="telemetry-cell">
            <span>System</span>
            <strong class="is-live">Operational</strong>
          </div>
          <div class="telemetry-cell">
            <span>Mode</span>
            <strong :style="{ color: modeColor }">{{ runMode }}</strong>
          </div>
          <div class="telemetry-cell">
            <span>Regime</span>
            <strong :style="{ color: regimeColor }">{{ regimeLabel }}</strong>
          </div>
          <div class="telemetry-cell">
            <span>Last Scan</span>
            <strong>{{ marketMeta.updated || '—' }}</strong>
          </div>
          <div class="telemetry-cell">
            <span>Freshness</span>
            <strong>{{ marketMeta.freshness?.market || '—' }}</strong>
          </div>
          <div class="telemetry-cell clock-cell">
            <span>Asia/Shanghai</span>
            <strong>{{ clock }}</strong>
          </div>
        </div>
      </header>

      <main class="content-plane">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>

      <footer class="market-ticker">
        <span class="ticker-label">MARKET TICKER</span>
        <span v-for="item in ticker" :key="item.symbol" class="ticker-item">
          <em>{{ item.symbol }}<b v-if="item.data_source === 'proxy'" class="ticker-proxy">p</b></em>
          <strong :style="{ color: item.change >= 0 ? 'var(--positive)' : 'var(--negative)' }">{{ item.value }}</strong>
          <small :style="{ color: item.change >= 0 ? 'var(--positive)' : 'var(--negative)' }">{{ item.change >= 0 ? '+' : '' }}{{ item.change.toFixed(2) }}%</small>
        </span>
        <span class="ticker-connection">CONNECTED</span>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import { useRoute } from "vue-router";
import { useParticles } from "./charts/particles";
import { api } from "./api";
import type { RegimeResponse } from "./api";

const route = useRoute();
const hovered = ref("");
const clock = ref("");
let clockTimer = 0;
let regimeTimer = 0;
const regime = ref<{ value: string; score?: number }>({ value: "sideways" });
const marketMeta = ref<Partial<RegimeResponse>>({});
const runMode = ref("research");

const nav = [
  { path: "/", label: "市场总览", pathData: "M4 17V7l8-4 8 4v10l-8 4-8-4Zm4-1 4 2 4-2V9l-4-2-4 2v7Zm2-1.5h4M10 11h4" },
  { path: "/strategies", label: "策略中心", pathData: "M12 3l8 4v10l-8 4-8-4V7l8-4Zm0 4v10M7 9.5l5 2.5 5-2.5" },
  { path: "/stocks", label: "个股深挖", pathData: "M4 18l5-5 4 3 7-9M4 6h16M4 21h16" },
  { path: "/portfolio", label: "模拟交易", pathData: "M5 7h14v12H5V7Zm3 0V5h8v2M8 13h3m2 0h3" },
  { path: "/backtest", label: "回测分析", pathData: "M4 19V5m0 14h16M7 15l3-4 3 2 5-7" },
  { path: "/signals", label: "信号历史", pathData: "M12 20a8 8 0 1 0-8-8m8 8V9m0 0 4 4m-4-4-4 4" },
  { path: "/monitor", label: "系统信息", pathData: "M4 13h3l2-6 4 12 2-6h5M4 20h16M4 4h16" },
  { path: "/db-health", label: "数据库健康", pathData: "M4 6h16M4 12h16M4 18h16M8 2v4m0 4v4m8-12v4m0 4v4M4 22h16" },
  { path: "/hindsight", label: "记忆图谱", pathData: "M12 2a5 5 0 0 0-5 5v1a5 5 0 0 0 0 10v1a5 5 0 0 0 10 0v-1a5 5 0 0 0 0-10V7a5 5 0 0 0-5-5Zm-3 5a3 3 0 1 1 6 0v1h-6V7Zm6 10a3 3 0 1 1-6 0v-1h6v1ZM9 16a4 4 0 0 1 6 0M8 10h8M8 14h8" },
  { path: "/settings", label: "系统设置", pathData: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-7.5-2.2-.7-.7a1.5 1.5 0 0 1 0-2.1l.7-.7L3 7.8l-.7.7a1.5 1.5 0 0 1-2.1 0l-.7-.7-.7.7 1.5 1.5-.7.7a1.5 1.5 0 0 1 0 2.1l.7.7.7-.7L3 15.3l1.5 1.5ZM21 15a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" },
];

const routeTitle = computed(() => nav.find(item => isActive(item.path))?.label || "Quant Terminal");

const ticker = computed(() => (marketMeta.value.multi_asset || []).map((item: any) => ({
  symbol: item.symbol,
  value: item.value == null ? "—" : `${Number(item.value).toFixed(item.unit === "%" ? 3 : 2)}${item.unit || ""}`,
  change: (item.change_pct || 0) * 100,
  data_source: item.data_source || "real",
})));

const regimeLabel = computed(() => {
  if (regime.value.value === "bull") return "BULL";
  if (regime.value.value === "bear") return "BEAR";
  return "SIDEWAYS";
});

const regimeColor = computed(() => {
  if (regime.value.value === "bull") return "var(--positive)";
  if (regime.value.value === "bear") return "var(--negative)";
  return "var(--warning)";
});
const modeColor = computed(() => {
  if (runMode.value === "live") return "var(--negative)";
  if (runMode.value === "paper") return "var(--warning)";
  return "var(--positive)";
});
const coreVersion = computed(() => {
  const version = (marketMeta.value.config as any)?.project?.version;
  return version ? `v${version}` : "v—";
});

function tickClock() {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  clock.value = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}

function isActive(path: string) {
  if (path === "/") return route.path === "/";
  return route.path.startsWith(path);
}

async function fetchRegime() {
  try {
    const data = await api.marketRegime();
    regime.value = data.regime;
    marketMeta.value = data;
  } catch {}
}

async function fetchMode() {
  try {
    const data = await api.systemMode();
    runMode.value = data.mode;
  } catch {}
}

// Particles
useParticles();

onMounted(() => {
  tickClock();
  clockTimer = window.setInterval(tickClock, 1000);
  fetchRegime();
  fetchMode();
  regimeTimer = window.setInterval(fetchRegime, 60000);
});

onUnmounted(() => {
  clearInterval(clockTimer);
  clearInterval(regimeTimer);
});
</script>

<style scoped>
/* Page transition */
.page-enter-active,
.page-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(4px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* Active nav glow */
.active { box-shadow: 0 0 18px rgba(38, 208, 255, 0.16); }
</style>
