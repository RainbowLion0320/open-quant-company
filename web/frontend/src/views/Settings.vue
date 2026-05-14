<template>
  <div class="p-6 space-y-6">
    <h1 class="text-lg font-semibold text-white/90">系统设置</h1>
    <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
      <h2 class="text-sm font-medium text-white/60 mb-4">通知设置</h2>
      <div class="space-y-3 text-sm">
        <label class="flex items-center gap-3">
          <input v-model="telegramEnabled" type="checkbox" class="accent-[#7170ff]" />
          <span class="text-white/70">Telegram 推送</span>
        </label>
        <label class="flex items-center gap-3">
          <input v-model="signalChangeOnly" type="checkbox" class="accent-[#7170ff]" />
          <span class="text-white/70">仅推送信号变更</span>
        </label>
      </div>
    </div>
    <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
      <h2 class="text-sm font-medium text-white/60 mb-4">数据源</h2>
      <div class="text-xs text-white/40 space-y-1">
        <div>日线行情: AKShare (Sina/EastMoney/Tencent)</div>
        <div>财务数据: Tushare (2000积分)</div>
        <div>数据库: DuckDB (列存引擎)</div>
        <div>行业分类: 申万2021版</div>
      </div>
    </div>
    <button @click="save" class="px-6 py-2 text-sm rounded bg-[#7170ff] hover:bg-[#8b8aff]">保存设置</button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";

const telegramEnabled = ref(true);
const signalChangeOnly = ref(true);

onMounted(async () => {
  try {
    const res = await fetch("/api/settings");
    const d = await res.json();
    const n = d.trading?.notification || {};
    telegramEnabled.value = n.enabled !== false;
    signalChangeOnly.value = n.signal_change_only !== false;
  } catch {}
});

async function save() {
  try {
    const res = await fetch("/api/settings");
    const d = await res.json();
    d.trading = d.trading || {};
    d.trading.notification = d.trading.notification || {};
    d.trading.notification.enabled = telegramEnabled.value;
    d.trading.notification.signal_change_only = signalChangeOnly.value;
    await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(d),
    });
  } catch {}
}
</script>
