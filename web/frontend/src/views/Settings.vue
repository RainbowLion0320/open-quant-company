<template>
  <div class="p-6 space-y-5">
    <div class="page-header">
      <div>
        <h1 class="page-title">系统设置</h1>
        <p class="page-subtitle">通知配置 · 数据源状态 · 系统信息</p>
      </div>
      <button @click="save" class="btn btn-primary btn-sm">保存</button>
    </div>

    <!-- Notification -->
    <div class="glass-card" style="padding:20px">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">Telegram 通知</div>
      <div class="flex items-center justify-between">
        <div>
          <div class="text-sm" style="color:var(--text-primary)">启用信号推送</div>
          <div class="text-[11px] mt-0.5" style="color:var(--text-disabled)">每日 15:30 扫描后推送信号变更到 @buffett0320_bot</div>
        </div>
        <button @click="toggleNotify" class="relative w-10 h-5 rounded-full transition-colors"
          :style="{ background: settings.trading?.notification?.enabled ? 'var(--accent)' : 'var(--border-strong)' }">
          <span class="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform"
            :style="{ left: settings.trading?.notification?.enabled ? '22px' : '2px' }">
          </span>
        </button>
      </div>
    </div>

    <!-- Data Sources -->
    <div class="glass-card" style="padding:20px">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">数据源</div>
      <div class="space-y-3">
        <div class="flex justify-between items-center py-2 border-b" style="border-color:var(--border-subtle)">
          <span class="text-sm" style="color:var(--text-primary)">AKShare</span>
          <span class="badge badge-green">正常</span>
        </div>
        <div class="flex justify-between items-center py-2 border-b" style="border-color:var(--border-subtle)">
          <span class="text-sm" style="color:var(--text-primary)">Tushare MCP</span>
          <span class="badge badge-green">正常</span>
        </div>
        <div class="flex justify-between items-center py-2">
          <span class="text-sm" style="color:var(--text-primary)">Parquet 存储</span>
          <span class="badge badge-green">正常</span>
        </div>
      </div>
    </div>

    <!-- System Info -->
    <div class="glass-card" style="padding:20px">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">系统信息</div>
      <div class="grid grid-cols-2 gap-3 text-xs">
        <div class="flex justify-between py-2 border-b" style="border-color:var(--border-subtle)">
          <span style="color:var(--text-disabled)">版本</span>
          <span class="font-mono" style="color:var(--text-secondary)">v4.0 Quantum Terminal</span>
        </div>
        <div class="flex justify-between py-2 border-b" style="border-color:var(--border-subtle)">
          <span style="color:var(--text-disabled)">API 端口</span>
          <span class="font-mono" style="color:var(--text-secondary)">8501</span>
        </div>
        <div class="flex justify-between py-2 border-b" style="border-color:var(--border-subtle)">
          <span style="color:var(--text-disabled)">股票池</span>
          <span class="font-mono" style="color:var(--text-secondary)">1000 只</span>
        </div>
        <div class="flex justify-between py-2 border-b" style="border-color:var(--border-subtle)">
          <span style="color:var(--text-disabled)">策略数</span>
          <span class="font-mono" style="color:var(--text-secondary)">4 (巴菲特/多因子/控制论/ML)</span>
        </div>
        <div class="flex justify-between py-2 border-b" style="border-color:var(--border-subtle)">
          <span style="color:var(--text-disabled)">因子数</span>
          <span class="font-mono" style="color:var(--text-secondary)">26 (alpha_factors) + 14 = 40 全特征</span>
        </div>
        <div class="flex justify-between py-2 border-b" style="border-color:var(--border-subtle)">
          <span style="color:var(--text-disabled)">ML 模型</span>
          <span class="font-mono" style="color:var(--text-secondary)">LightGBM · IC=0.097 (CV)</span>
        </div>
        <div class="flex justify-between py-2">
          <span style="color:var(--text-disabled)">Cron</span>
          <span class="font-mono" style="color:var(--text-secondary)">每交易日 15:30 CST</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, onMounted } from "vue";
import { api } from "../api";

const settings = reactive<Record<string, any>>({});

async function toggleNotify() {
  const enabled = !settings.trading?.notification?.enabled;
  settings.trading = settings.trading || {};
  settings.trading.notification = settings.trading.notification || {};
  settings.trading.notification.enabled = enabled;
  await save();
}

async function save() {
  try { await api.saveSettings(settings); } catch {}
}

onMounted(async () => {
  try {
    const data = await api.settings();
    Object.assign(settings, data);
  } catch {}
});
</script>
