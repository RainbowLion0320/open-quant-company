<template>
  <div class="p-6 space-y-5">
    <div class="page-header">
      <div>
        <h1 class="page-title">信号历史</h1>
        <p class="page-subtitle">最近 7 天信号变更追踪</p>
      </div>
    </div>

    <div class="glass-card" style="padding:20px">
      <table class="data-table" v-if="changes.length">
        <thead>
          <tr>
            <th>日期</th><th>策略</th><th>代码</th><th>名称</th>
            <th class="text-right">旧信号</th><th class="text-right">新信号</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(c, i) in changes" :key="i">
            <td class="font-mono" style="color:var(--text-disabled)">{{ c.date?.slice(0, 10) }}</td>
            <td style="color:var(--text-secondary)">{{ c.strategy }}</td>
            <td class="font-mono">{{ c.symbol }}</td>
            <td>{{ c.name }}</td>
            <td class="text-right">
              <span :style="{ color: signalColor(c.old_signal) }">{{ signalLabel(c.old_signal) }}</span>
            </td>
            <td class="text-right">
              <span :style="{ color: signalColor(c.new_signal), fontWeight: c.new_signal !== c.old_signal ? '600' : '400' }">
                <span v-if="c.new_signal !== c.old_signal" style="color:var(--positive); margin-right:4px">↑</span>
                {{ signalLabel(c.new_signal) }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state">
        <span>暂无信号变更记录</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api";
import type { SignalChange } from "../api";

const changes = ref<SignalChange[]>([]);

function signalColor(s: string) {
  if (s === "buy") return "var(--positive)";
  if (s === "sell") return "var(--negative)";
  return "var(--text-disabled)";
}
function signalLabel(s: string) {
  if (s === "buy") return "买入";
  if (s === "sell") return "卖出";
  return "持有";
}

onMounted(async () => {
  try { changes.value = await api.signalChanges(7); } catch {}
});
</script>
