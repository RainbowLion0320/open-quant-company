<template>
  <div class="p-6 space-y-6">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold text-white/90">策略中心</h1>
      <button
        @click="runStrategy"
        :disabled="store.running"
        class="px-4 py-2 text-sm rounded bg-[#7170ff] hover:bg-[#8b8aff] disabled:opacity-40 transition-colors"
      >
        {{ store.running ? `运行中 ${store.progress}%` : '运行全部策略' }}
      </button>
    </div>

    <!-- 进度条 -->
    <div v-if="store.running" class="bg-[#111214] border border-white/5 rounded-lg p-4">
      <div class="text-xs text-white/50 mb-2">{{ store.progressMsg }}</div>
      <div class="w-full bg-white/5 rounded-full h-1.5">
        <div class="bg-[#7170ff] h-1.5 rounded-full transition-all" :style="{ width: store.progress + '%' }"></div>
      </div>
    </div>

    <!-- 策略卡片 -->
    <div v-for="s in store.strategies" :key="s.name" class="bg-[#111214] border border-white/5 rounded-lg p-4">
      <div class="flex items-center justify-between mb-3">
        <div>
          <h2 class="text-sm font-medium text-white/80">{{ s.label }}</h2>
          <div class="text-xs text-white/40 mt-1">
            {{ s.total }} 只股票 · {{ s.buys }} 只买入
            <span v-if="s.last_computed" class="ml-3">更新: {{ s.last_computed?.slice(0, 16) }}</span>
          </div>
        </div>
        <div class="flex gap-2">
          <button @click="loadSignals(s.name)" class="px-3 py-1.5 text-xs rounded bg-white/5 hover:bg-white/10">
            查看信号
          </button>
          <button @click="runSingle(s.name)" class="px-3 py-1.5 text-xs rounded bg-[#7170ff]/20 hover:bg-[#7170ff]/30 text-[#7170ff]">
            运行
          </button>
        </div>
      </div>

      <!-- 信号表格 -->
      <div v-if="currentStrategy === s.name && signals.length" class="mt-4">
        <table class="w-full text-xs">
          <thead>
            <tr class="text-white/40 border-b border-white/5">
              <th class="text-left py-2 pr-4">代码</th>
              <th class="text-left py-2 pr-4">名称</th>
              <th class="text-left py-2 pr-4">行业</th>
              <th class="text-right py-2 pr-4">评分</th>
              <th class="text-right py-2">信号</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="sig in signals.slice(0, 20)" :key="sig.symbol" class="border-b border-white/[0.02] hover:bg-white/[0.02]">
              <td class="py-2 pr-4 font-mono text-white/50">{{ sig.symbol }}</td>
              <td class="py-2 pr-4">
                <router-link :to="`/stocks/${sig.symbol}`" class="text-white/70 hover:text-[#7170ff]">
                  {{ sig.name }}
                </router-link>
              </td>
              <td class="py-2 pr-4 text-white/40">{{ sig.industry }}</td>
              <td class="py-2 pr-4 text-right font-mono">{{ sig.score?.toFixed(1) }}</td>
              <td class="py-2 text-right">
                <span :class="sig.signal === 'buy' ? 'text-green-400' : 'text-white/30'">
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

async function loadSignals(name: string) {
  currentStrategy.value = name;
  await store.fetchSignals(name);
  signals.value = store.signals[name] || [];
}

function runStrategy() {
  store.run("all");
}

function runSingle(name: string) {
  store.run(name);
}

onMounted(() => store.fetchList());
</script>
