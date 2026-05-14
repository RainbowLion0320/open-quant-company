<template>
  <div class="p-6 space-y-6">
    <h1 class="text-lg font-semibold text-white/90">信号历史</h1>
    <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
      <p class="text-white/40 text-sm">信号变更追溯 — 每日扫描后自动记录信号变化（买入↔持有）</p>
    </div>
    <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
      <h2 class="text-sm font-medium text-white/60 mb-4">最近7天信号变更</h2>
      <div v-if="changes.length" class="space-y-2">
        <div v-for="c in changes" :key="c.symbol + c.date" class="flex items-center gap-3 text-xs py-2 border-b border-white/[0.02]">
          <span class="font-mono text-white/50 w-16">{{ c.symbol }}</span>
          <span class="text-white/70 w-20">{{ c.name }}</span>
          <span class="w-16 px-2 py-0.5 rounded text-center text-[10px]" :class="c.to_signal === 'buy' ? 'bg-green-400/10 text-green-400' : 'bg-white/5 text-white/40'">{{ c.to_signal === 'buy' ? '→买入' : '→持有' }}</span>
          <span class="text-white/30">{{ c.strategy }}</span>
          <span class="text-white/20 ml-auto">{{ c.date }}</span>
        </div>
      </div>
      <p v-else class="text-white/30 text-sm py-4">暂无变更记录</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
const changes = ref<any[]>([]);
onMounted(async () => {
  try {
    const res = await fetch("/api/signals/changes?days=7");
    changes.value = await res.json();
  } catch {}
});
</script>
