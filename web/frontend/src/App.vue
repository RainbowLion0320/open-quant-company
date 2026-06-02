<template>
  <div class="app-shell">
    <div class="orbital-grid"></div>
    <div class="scanline"></div>

    <aside class="nav-rail">
      <div class="brand-mark" role="img" :aria-label="t('app.brand')">
        <img :src="logoUrl" alt="" aria-hidden="true" />
      </div>

      <nav class="nav-stack" :aria-label="t('app.navAria')">
        <router-link
          v-for="item in nav"
          :key="item.path"
          :to="item.path"
          class="nav-node"
          :class="{ active: isActive(item.path) }"
          @mouseenter="hovered = item.labelKey"
          @mouseleave="hovered = ''"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path :d="item.pathData" />
          </svg>
          <span class="nav-tooltip">{{ t(item.labelKey) }}</span>
        </router-link>
      </nav>

      <button
        class="locale-toggle"
        type="button"
        :aria-label="t('app.languageSwitch')"
        :title="t('app.languageSwitch')"
        @click="toggleLocale"
      >
        <span :class="{ active: currentLocale === 'zh-CN' }">中</span>
        <span :class="{ active: currentLocale === 'en-US' }">EN</span>
      </button>

      <div class="core-status">
        <span>{{ t('app.build') }}</span>
        <strong>{{ buildVersion }}</strong>
      </div>
    </aside>

    <section class="workspace">
      <header class="command-bar">
        <div class="system-title">
          <strong>{{ routeTitle }}</strong>
          <span class="system-kicker">ASTROLABE QUANT OS</span>
        </div>
      </header>

      <main class="content-plane">
        <router-view v-slot="{ Component }">
          <transition name="page" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>

      <footer class="system-statusbar" :aria-label="t('app.statusAria')">
        <div class="statusbar-telemetry">
          <div class="telemetry-tag">
            <span>{{ t('app.mode') }}</span>
            <strong :style="{ color: modeColor }">{{ runMode }}</strong>
          </div>
          <div class="telemetry-tag">
            <span>{{ t('app.regime') }}</span>
            <strong :style="{ color: regimeColor }">{{ regimeLabel }}</strong>
          </div>
          <div class="telemetry-tag">
            <span>{{ t('app.fresh') }}</span>
            <strong>{{ marketMeta.freshness?.market || '—' }}</strong>
          </div>
        </div>
        <div class="statusbar-health" :title="systemLabel">
          <span class="status-dot" :style="{ '--dot-color': systemColor }"></span>
          <strong>{{ systemLabel }}</strong>
        </div>
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
import { useI18n } from "./i18n";
import logoUrl from "./assets/astrolabe-logo.svg";

const route = useRoute();
const { currentLocale, t, toggleLocale } = useI18n();
const hovered = ref("");
let regimeTimer = 0;
const regime = ref<{ value: string; score?: number }>({ value: "sideways" });
const marketMeta = ref<Partial<RegimeResponse>>({});
const runMode = ref("research");
const systemHealth = ref<{ all_ok: boolean; ok_count: number; total: number }>({ all_ok: true, ok_count: 0, total: 0 });

const nav = [
  { path: "/", labelKey: "nav.market", pathData: "M4 17V7l8-4 8 4v10l-8 4-8-4Zm4-1 4 2 4-2V9l-4-2-4 2v7Zm2-1.5h4M10 11h4" },
  { path: "/research", labelKey: "nav.research", pathData: "M3 18l5-5 4 3 7-9M4 6h16M4 21h16M7 11h3m4 7h3" },
  { path: "/strategy-lab", labelKey: "nav.strategyLab", pathData: "M12 3l8 4v10l-8 4-8-4V7l8-4Zm0 4v10M7 9.5l5 2.5 5-2.5M8 17l4-2 4 2" },
  { path: "/portfolio", labelKey: "nav.portfolio", pathData: "M5 7h14v12H5V7Zm3 0V5h8v2M8 13h3m2 0h3M8 16h8" },
  { path: "/pipeline", labelKey: "nav.pipeline", pathData: "M5 5h5v5H5V5Zm9 0h5v5h-5V5ZM5 14h5v5H5v-5Zm9 0h5v5h-5v-5ZM10 7.5h4M7.5 10v4M16.5 10v4M10 16.5h4" },
  { path: "/datahub", labelKey: "nav.datahub", pathData: "M4 6c0-2 16-2 16 0v12c0 2-16 2-16 0V6Zm0 0c0 2 16 2 16 0M4 12c0 2 16 2 16 0M4 18c0 2 16 2 16 0" },
  { path: "/system", labelKey: "nav.system", pathData: "M4 13h3l2-6 4 12 2-6h5M4 20h16M4 4h16M17 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" },
];

const activeSectionPath = computed(() => {
  if (route.path === "/") return "/";
  if (route.path.startsWith("/research") || route.path.startsWith("/stocks")) return "/research";
  if (route.path.startsWith("/strategy-lab")) return "/strategy-lab";
  if (route.path.startsWith("/portfolio")) return "/portfolio";
  if (route.path.startsWith("/pipeline")) return "/pipeline";
  if (route.path.startsWith("/datahub")) return "/datahub";
  if (route.path.startsWith("/system")) return "/system";
  return route.path;
});

const routeTitle = computed(() => {
  const item = nav.find(item => item.path === activeSectionPath.value);
  return item ? t(item.labelKey) : t("app.fallbackTitle");
});

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
  if (systemHealth.value.total === 0) return t("app.health.unknown");
  if (systemHealth.value.all_ok) return t("app.health.operational");
  if (systemHealth.value.ok_count === 0) return t("app.health.down");
  return t("app.health.degraded");
});
const systemColor = computed(() => {
  if (systemHealth.value.total === 0) return "var(--text-muted)";
  if (systemHealth.value.all_ok) return "var(--positive)";
  if (systemHealth.value.ok_count === 0) return "var(--negative)";
  return "var(--warning)";
});
const buildVersion = computed(() => {
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

.locale-toggle {
  width: 48px;
  height: 30px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.16);
  color: var(--text-disabled);
  cursor: pointer;
}

.locale-toggle span {
  display: grid;
  place-items: center;
  border-radius: 5px;
  font-family: "JetBrains Mono", monospace;
  font-size: 9px;
  font-weight: 700;
  line-height: 1;
}

.locale-toggle span.active {
  background: rgba(0, 212, 255, 0.14);
  color: var(--accent);
  box-shadow: inset 0 0 0 1px rgba(0, 212, 255, 0.16);
}

@media (max-width: 980px) {
  .locale-toggle {
    flex-shrink: 0;
    width: 50px;
    height: 34px;
  }
}
</style>
