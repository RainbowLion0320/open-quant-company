<template>
  <div class="flex h-screen" style="background:var(--bg-root)">
    <!-- 侧边栏 — 72px 纯图标 -->
    <aside class="w-[72px] border-r flex flex-col shrink-0 items-center"
      style="background:var(--bg-panel); border-color:var(--border-subtle)">

      <!-- Logo -->
      <div class="h-12 flex items-center justify-center w-full border-b" style="border-color:var(--border-subtle)">
        <span class="text-xs font-bold tracking-wider" style="color:var(--accent)">QA</span>
      </div>

      <!-- Nav -->
      <nav class="flex-1 py-3 w-full flex flex-col items-center gap-1">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="relative flex items-center justify-center w-11 h-11 rounded-lg transition-all duration-150 group"
          :style="$route.path === item.path
            ? { color: 'var(--text-primary)', background: 'var(--accent-bg)' }
            : { color: 'var(--text-quaternary)' }"
          @mouseenter="hovered = item.label"
          @mouseleave="hovered = ''"
        >
          <span class="text-lg leading-none" :style="$route.path === item.path ? {} : { opacity: 0.55 }">{{ item.icon }}</span>
          <!-- Active indicator -->
          <span v-if="$route.path === item.path"
            class="absolute left-0 top-2 bottom-2 w-0.5 rounded-r"
            style="background:var(--accent)">
          </span>
          <!-- Tooltip -->
          <span v-if="hovered === item.label"
            class="absolute left-full ml-3 px-2.5 py-1.5 rounded-md text-xs font-medium whitespace-nowrap z-50 pointer-events-none"
            style="background:var(--bg-surface); color:var(--text-primary); border:1px solid var(--border-default); box-shadow:0 4px 12px rgba(0,0,0,0.4)">
            {{ item.label }}
          </span>
        </router-link>
      </nav>

      <!-- Version -->
      <div class="pb-4 w-full flex justify-center">
        <span class="text-[9px] tracking-wider" style="color:var(--text-quaternary)">v2</span>
      </div>
    </aside>

    <!-- 主内容 -->
    <main class="flex-1 overflow-auto">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";

const hovered = ref("");

const navItems = [
  { path: "/", label: "市场总览", icon: "📊" },
  { path: "/strategies", label: "策略中心", icon: "🎯" },
  { path: "/portfolio", label: "模拟交易", icon: "💼" },
  { path: "/stocks", label: "个股深挖", icon: "🔍" },
  { path: "/backtest", label: "回测分析", icon: "📈" },
  { path: "/signals", label: "信号历史", icon: "📡" },
  { path: "/settings", label: "系统设置", icon: "⚙️" },
];
</script>
