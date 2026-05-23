<template>
  <div class="view-page">
    <div class="surface-toolbar">
      <div class="surface-copy">
        <span>SIGNAL CHANGELOG</span>
        <strong>最近 {{ days }} 天变更</strong>
        <small>观察新增买入、降级和不同策略之间的信号迁移</small>
      </div>
      <div class="surface-actions">
        <div class="filter-tabs" aria-label="信号时间范围">
          <button
            v-for="d in dayOptions"
            :key="d"
            :class="{ active: days === d }"
            @click="selectDays(d)"
          >{{ d }}D</button>
        </div>
      </div>
    </div>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="loadChanges">重试</button>
    </div>

    <div class="glass-card card-pad-lg">
      <div v-if="loading" class="empty-state empty-state-compact">正在加载信号变更...</div>
      <div v-else-if="changes.length" class="table-shell" style="--table-min:680px">
        <table class="data-table">
          <colgroup>
            <col style="width:14%">
            <col style="width:16%">
            <col style="width:14%">
            <col style="width:22%">
            <col style="width:17%">
            <col style="width:17%">
          </colgroup>
          <thead>
            <tr>
              <th>日期</th>
              <th>策略</th>
              <th>代码</th>
              <th>名称</th>
              <th class="text-right">旧信号</th>
              <th class="text-right">新信号</th>
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
      </div>
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
const days = ref(7);
const dayOptions = [7, 14, 30];
const loading = ref(false);
const error = ref("");

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

async function loadChanges() {
  loading.value = true;
  error.value = "";
  try {
    changes.value = await api.signalChanges(days.value);
  } catch (e: any) {
    error.value = e?.message || "信号变更加载失败";
    changes.value = [];
  } finally {
    loading.value = false;
  }
}

function selectDays(d: number) {
  if (days.value === d) return;
  days.value = d;
  loadChanges();
}

onMounted(loadChanges);
</script>
