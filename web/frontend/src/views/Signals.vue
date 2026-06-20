<template>
  <div class="view-page">
    <div class="compact-action-row">
      <div class="filter-tabs" :aria-label="t('signals.rangeAria')">
        <button
          v-for="d in dayOptions"
          :key="d"
          :class="{ active: days === d }"
          @click="selectDays(d)"
        >{{ d }}D</button>
      </div>
    </div>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="loadChanges">{{ t('common.retry') }}</button>
    </div>

    <div class="glass-card card-pad-lg">
      <div v-if="loading" class="empty-state empty-state-compact">{{ t('signals.loading') }}</div>
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
              <th>{{ t('portfolio.table.date') }}</th>
              <th>{{ t('common.strategy') }}</th>
              <th>{{ t('portfolio.table.code') }}</th>
              <th>{{ t('portfolio.table.name') }}</th>
              <th class="text-right">{{ t('signals.oldSignal') }}</th>
              <th class="text-right">{{ t('signals.newSignal') }}</th>
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
        <span>{{ t('signals.empty') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api";
import type { SignalChange } from "../api";
import { useI18n } from "../i18n";
import { signalLabel as formatSignalLabel } from "../utils/signals";

const { t } = useI18n();
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
  return formatSignalLabel(s, t);
}

async function loadChanges() {
  loading.value = true;
  error.value = "";
  try {
    changes.value = await api.signalChanges(days.value);
  } catch (e: any) {
    error.value = e?.message || t("signals.loadError");
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
