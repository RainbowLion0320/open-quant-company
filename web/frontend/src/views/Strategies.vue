<template>
  <div class="p-6 space-y-5">
    <div class="page-header">
      <div>
        <h1 class="page-title">策略中心</h1>
        <p class="page-subtitle">扫描控制台 · 信号查看 · 手动触发</p>
      </div>
      <button @click="runAll" :disabled="store.running" class="btn btn-primary btn-sm">
        {{ store.running ? `运行中 ${store.progress}%` : '运行全部' }}
      </button>
    </div>

    <!-- Progress Bar -->
    <div v-if="store.running" class="glass-card" style="padding:14px 18px">
      <div class="text-xs mb-2" style="color:var(--text-secondary)">{{ store.progressMsg }}</div>
      <div class="progress-bar">
        <div class="progress-bar-fill" :style="{ width: store.progress + '%' }"></div>
      </div>
    </div>

    <!-- Strategy Cards -->
    <div v-for="s in store.strategies" :key="s.name" class="glass-card glow-cyan animate-fade-in" style="padding:18px">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-3">
          <div class="w-2 h-2 rounded-full" :style="{ background: colorFor(s.name), boxShadow: `0 0 6px ${colorFor(s.name)}` }"></div>
          <div>
            <h2 class="text-sm font-semibold" style="color:var(--text-primary)">{{ s.label }}</h2>
            <div class="text-[11px] mt-0.5" style="color:var(--text-disabled)">
              {{ s.total }} 只扫描 · {{ s.buys }} 只买入
              <span v-if="s.last_computed" class="ml-3">⏱ {{ s.last_computed?.slice(0, 16) }}</span>
            </div>
          </div>
        </div>
        <div class="flex gap-2">
          <button @click="toggleSignals(s.name)" class="btn btn-sm btn-ghost">信号</button>
          <button @click="runSingle(s.name)" class="btn btn-sm" style="border-color:rgba(0,212,255,0.2); color:var(--accent)">运行</button>
        </div>
      </div>

      <!-- Signal Table -->
      <div v-if="currentStrategy === s.name && signals.length" class="mt-4 animate-fade-in">
        <table class="data-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th>行业</th>
              <th class="text-right">评分</th>
              <th class="text-right">信号</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sig in signals.slice(0, 20)" :key="sig.symbol">
              <td class="font-mono">{{ sig.symbol }}</td>
              <td>
                <router-link :to="`/stocks/${sig.symbol}`" class="hover:underline" style="color:var(--accent)">
                  {{ sig.name }}
                </router-link>
              </td>
              <td>{{ sig.industry }}</td>
              <td class="text-right font-mono">{{ sig.score?.toFixed(1) }}</td>
              <td class="text-right">
                <span :style="{ color: sig.signal === 'buy' ? 'var(--positive)' : 'var(--text-disabled)' }">
                  {{ sig.signal === 'buy' ? '买入' : '持有' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useStrategyStore } from "../stores";

const store = useStrategyStore();
const currentStrategy = ref("");
const signals = ref<any[]>([]);

const strategyColors: Record<string, string> = {
  buffett: "#00d4ff",
  multifactor: "#22c55e",
  cybernetic: "#eab308",
  ml_lgbm: "#7c3aed",
};
function colorFor(name: string) { return strategyColors[name] || "var(--accent)"; }

async function toggleSignals(name: string) {
  if (currentStrategy.value === name) { currentStrategy.value = ""; signals.value = []; return; }
  currentStrategy.value = name;
  await store.fetchSignals(name);
  signals.value = store.signals[name] || [];
}

function runAll() { store.run("all"); }
function runSingle(name: string) { store.run(name); }

onMounted(() => store.fetchList());
</script>
