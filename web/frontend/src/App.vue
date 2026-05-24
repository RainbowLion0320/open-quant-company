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
        <div class="telemetry-group">
          <div class="telemetry-tag">
            <span>MODE</span>
            <strong :style="{ color: modeColor }">{{ runMode }}</strong>
          </div>
          <div class="telemetry-tag">
            <span>REGIME</span>
            <strong :style="{ color: regimeColor }">{{ regimeLabel }}</strong>
          </div>
          <div class="telemetry-tag">
            <span>FRESH</span>
            <strong>{{ marketMeta.freshness?.market || '—' }}</strong>
          </div>
          <div class="system-status" :title="systemLabel">
            <span class="status-dot" :style="{ '--dot-color': systemColor }"></span>
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
let regimeTimer = 0;
const regime = ref<{ value: string; score?: number }>({ value: "sideways" });
const marketMeta = ref<Partial<RegimeResponse>>({});
const runMode = ref("research");
const systemHealth = ref<{ all_ok: boolean; ok_count: number; total: number }>({ all_ok: true, ok_count: 0, total: 0 });

const nav = [
  { path: "/", label: "市场总览", pathData: "M4 17V7l8-4 8 4v10l-8 4-8-4Zm4-1 4 2 4-2V9l-4-2-4 2v7Zm2-1.5h4M10 11h4" },
  { path: "/research", label: "市场研究", pathData: "M3 18l5-5 4 3 7-9M4 6h16M4 21h16M7 11h3m4 7h3" },
  { path: "/strategy-lab", label: "策略实验室", pathData: "M12 3l8 4v10l-8 4-8-4V7l8-4Zm0 4v10M7 9.5l5 2.5 5-2.5M8 17l4-2 4 2" },
  { path: "/portfolio", label: "组合执行", pathData: "M5 7h14v12H5V7Zm3 0V5h8v2M8 13h3m2 0h3M8 16h8" },
  { path: "/datahub", label: "数据中台", pathData: "M4 6c0-2 16-2 16 0v12c0 2-16 2-16 0V6Zm0 0c0 2 16 2 16 0M4 12c0 2 16 2 16 0M4 18c0 2 16 2 16 0" },
  { path: "/system", label: "系统控制", pathData: "M4 13h3l2-6 4 12 2-6h5M4 20h16M4 4h16M17 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" },
];

const activeSectionPath = computed(() => {
  if (route.path === "/") return "/";
  if (route.path.startsWith("/research") || route.path.startsWith("/stocks") || route.path.startsWith("/sectors")) return "/research";
  if (route.path.startsWith("/strategy-lab") || route.path.startsWith("/strategies") || route.path.startsWith("/signals") || route.path.startsWith("/backtest")) return "/strategy-lab";
  if (route.path.startsWith("/portfolio")) return "/portfolio";
  if (route.path.startsWith("/datahub") || route.path.startsWith("/db-health")) return "/datahub";
  if (route.path.startsWith("/system") || route.path.startsWith("/monitor") || route.path.startsWith("/settings") || route.path.startsWith("/hindsight")) return "/system";
  return route.path;
});

const routeTitle = computed(() => nav.find(item => item.path === activeSectionPath.value)?.label || "Quant Terminal");

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
const systemLabel = computed(() => {
  if (systemHealth.value.total === 0) return "Unknown";
  if (systemHealth.value.all_ok) return "Operational";
  if (systemHealth.value.ok_count === 0) return "Down";
  return "Degraded";
});
const systemColor = computed(() => {
  if (systemHealth.value.total === 0) return "var(--text-muted)";
  if (systemHealth.value.all_ok) return "var(--positive)";
  if (systemHealth.value.ok_count === 0) return "var(--negative)";
  return "var(--warning)";
});
const coreVersion = computed(() => {
  const version = (marketMeta.value.config as any)?.project?.version;
  return version ? `v${version}` : "v—";
});

function isActive(path: string) {
  return activeSectionPath.value === path;
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

async function fetchSystemHealth() {
  try {
    const data = await api.apiHealth();
    const okCount = (data.items || []).filter((i: any) => i.status === "ok").length;
    systemHealth.value = { all_ok: data.all_ok, ok_count: okCount, total: (data.items || []).length };
  } catch {}
}

// Particles
useParticles();

onMounted(() => {
  fetchRegime();
  fetchMode();
  fetchSystemHealth();
  regimeTimer = window.setInterval(fetchRegime, 60000);
});

onUnmounted(() => {
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
