<template>
  <div class="flex h-screen" style="background:var(--bg-void)">
    <!-- Scanline overlay -->
    <div class="scanline"></div>

    <!-- Floating Glass Sidebar -->
    <aside
      class="flex flex-col shrink-0 items-center py-4 gap-1 relative"
      style="width:72px; z-index:10;"
    >
      <!-- Logo -->
      <router-link to="/" class="flex items-center justify-center w-11 h-11 mb-2 rounded-xl"
        style="border:1px solid var(--accent); background:rgba(0,212,255,0.08); box-shadow:0 0 12px rgba(0,212,255,0.1)">
        <span class="text-xs font-bold tracking-wider" style="color:var(--accent)">QA</span>
      </router-link>

      <!-- Navigation -->
      <nav class="flex-1 flex flex-col items-center gap-1">
        <router-link
          v-for="item in nav"
          :key="item.path"
          :to="item.path"
          class="relative flex items-center justify-center w-11 h-11 rounded-xl transition-all duration-200 group"
          :class="active === item.path ? 'active' : ''"
          :style="active === item.path
            ? { color: 'var(--text-primary)', background: 'var(--bg-active)', border: '1px solid rgba(0,212,255,0.15)' }
            : { color: 'var(--text-disabled)' }"
          @mouseenter="hovered = item.label"
          @mouseleave="hovered = ''"
        >
          <span class="text-lg leading-none">{{ item.icon }}</span>

          <!-- Active glow bar -->
          <span v-if="active === item.path"
            class="absolute left-0 top-2 bottom-2 w-0.5 rounded-r animate-pulse-glow"
            style="background:var(--accent)">
          </span>

          <!-- Tooltip -->
          <span v-if="hovered === item.label"
            class="absolute left-full ml-3 px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap z-50 pointer-events-none animate-fade-in"
            style="background:var(--glass-bg); color:var(--text-primary); border:1px solid var(--border-strong); backdrop-filter:blur(12px);">
            {{ item.label }}
          </span>
        </router-link>
      </nav>

      <!-- Version -->
      <div class="w-full flex justify-center pb-2">
        <span class="text-[9px] tracking-wider font-mono" style="color:var(--text-disabled)">v4</span>
      </div>
    </aside>

    <!-- Main Content -->
    <main class="flex-1 overflow-auto relative" style="z-index:5">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- Bottom Status Bar -->
    <footer
      class="fixed bottom-0 left-0 right-0 flex items-center justify-between px-4 h-7 text-[10px] z-20"
      style="background:var(--bg-deep); border-top:1px solid var(--border-subtle); color:var(--text-tertiary)"
    >
      <div class="flex items-center gap-4">
        <span>QUANT AGENT v4.0</span>
        <span style="color:var(--border-strong)">|</span>
        <span :style="{ color: regimeColor }">{{ regimeLabel }}</span>
      </div>
      <div class="flex items-center gap-4 font-mono">
        <span>{{ clock }}</span>
        <span style="color:var(--border-strong)">|</span>
        <span>1000 股 · 4 策略 · 26 因子</span>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import { useRoute } from "vue-router";
import { useParticles } from "./charts/particles";
import { api } from "./api";

const route = useRoute();
const hovered = ref("");
const clock = ref("");
let clockTimer = 0;
let regimeTimer = 0;
const regime = ref<{ value: string }>({ value: "sideways" });

const active = computed(() => route.path);

const nav = [
  { path: "/", label: "市场总览", icon: "📊" },
  { path: "/strategies", label: "策略中心", icon: "🎯" },
  { path: "/portfolio", label: "模拟交易", icon: "💼" },
  { path: "/stocks", label: "个股深挖", icon: "🔍" },
  { path: "/backtest", label: "回测分析", icon: "📈" },
  { path: "/signals", label: "信号历史", icon: "📡" },
  { path: "/settings", label: "系统设置", icon: "⚙️" },
  { path: "/monitor", label: "活动监视", icon: "🖥️" },
];

const regimeLabel = computed(() => {
  if (regime.value.value === "bull") return "牛市 REGIME";
  if (regime.value.value === "bear") return "熊市 REGIME";
  return "震荡 REGIME";
});

const regimeColor = computed(() => {
  if (regime.value.value === "bull") return "var(--positive)";
  if (regime.value.value === "bear") return "var(--negative)";
  return "var(--warning)";
});

function tickClock() {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  clock.value = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())} CST`;
}

async function fetchRegime() {
  try {
    const data = await api.market();
    regime.value = data.regime;
  } catch {}
}

// Particles
useParticles();

onMounted(() => {
  tickClock();
  clockTimer = window.setInterval(tickClock, 1000);
  fetchRegime();
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
.active {
  box-shadow: 0 0 12px rgba(0, 212, 255, 0.1);
}
</style>
