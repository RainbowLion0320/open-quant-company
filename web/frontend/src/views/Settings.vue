<template>
  <div class="view-page settings-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">系统设置</h1>
        <p class="page-subtitle">通知配置 · 数据源状态 · 系统信息</p>
      </div>
      <button @click="save" class="btn btn-primary btn-sm">保存</button>
    </div>

    <!-- Notification -->
    <div class="glass-card card-pad-lg">
      <div class="section-heading mb-4">Telegram 通知</div>
      <div class="setting-row">
        <div>
          <strong>启用信号推送</strong>
          <span>每日 15:30 扫描后推送信号变更到 @buffett0320_bot</span>
        </div>
        <button @click="toggleNotify"
          class="settings-toggle"
          :class="{ active: settings.trading?.notification?.enabled }"
          aria-label="切换 Telegram 通知">
          <span></span>
        </button>
      </div>
    </div>

    <!-- Data Sources -->
    <div class="glass-card card-pad-lg">
      <div class="section-heading mb-4">数据源</div>
      <div class="settings-list">
        <div>
          <span>AKShare</span>
          <span class="badge badge-green">正常</span>
        </div>
        <div>
          <span>Tushare MCP</span>
          <span class="badge badge-green">正常</span>
        </div>
        <div>
          <span>Parquet 存储</span>
          <span class="badge badge-green">正常</span>
        </div>
      </div>
    </div>

    <!-- System Info -->
    <div class="glass-card card-pad-lg">
      <div class="section-heading mb-4">系统信息</div>
      <div class="settings-info-grid">
        <div>
          <span>版本</span>
          <strong>v5.1 Quantum Terminal</strong>
        </div>
        <div>
          <span>API 端口</span>
          <strong>8501</strong>
        </div>
        <div>
          <span>股票池</span>
          <strong>5204 只</strong>
        </div>
        <div>
          <span>策略数</span>
          <strong>4 active</strong>
        </div>
        <div>
          <span>因子数</span>
          <strong>35+</strong>
        </div>
        <div>
          <span>ML 模型</span>
          <strong>LightGBM · Regime-aware</strong>
        </div>
        <div>
          <span>Cron</span>
          <strong>每交易日 15:30 CST</strong>
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

<style scoped>
.settings-page {
  max-width: 980px;
}
.setting-row,
.settings-list div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.setting-row strong {
  display: block;
  color: var(--text-primary);
  font-size: 13px;
}
.setting-row span {
  display: block;
  margin-top: 3px;
  color: var(--text-disabled);
  font-size: 11px;
}
.settings-toggle {
  position: relative;
  width: 42px;
  height: 22px;
  flex: 0 0 auto;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--border-strong);
  cursor: pointer;
}
.settings-toggle span {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s ease;
}
.settings-toggle.active {
  background: var(--accent);
}
.settings-toggle.active span {
  transform: translateX(20px);
}
.settings-list {
  display: grid;
  gap: 0;
}
.settings-list div {
  min-height: 42px;
  border-bottom: 1px solid var(--border-subtle);
}
.settings-list div:last-child {
  border-bottom: 0;
}
.settings-list span:first-child {
  color: var(--text-primary);
  font-size: 13px;
}
.settings-info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.settings-info-grid div {
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: rgba(3, 10, 18, 0.24);
}
.settings-info-grid span {
  display: block;
  color: var(--text-disabled);
  font-size: 10px;
}
.settings-info-grid strong {
  display: block;
  margin-top: 4px;
  color: var(--text-secondary);
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (max-width: 720px) {
  .settings-info-grid {
    grid-template-columns: 1fr;
  }
  .setting-row {
    align-items: flex-start;
  }
}
</style>
