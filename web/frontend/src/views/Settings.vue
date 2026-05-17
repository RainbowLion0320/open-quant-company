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
          <span>{{ notificationText }}</span>
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
        <div v-for="src in sourceItems" :key="src.name">
          <span>{{ src.name }}</span>
          <span :class="['badge', sourceBadgeClass(src.status)]">{{ src.summary }}</span>
        </div>
        <div v-if="sourceItems.length === 0">
          <span>Registry</span>
          <span class="badge badge-muted">暂无配置</span>
        </div>
      </div>
    </div>

    <!-- System Info -->
    <div class="glass-card card-pad-lg">
      <div class="section-heading mb-4">系统信息</div>
      <div class="settings-info-grid">
        <div>
          <span>版本</span>
          <strong>{{ versionText }}</strong>
        </div>
        <div>
          <span>API 路由</span>
          <strong>/api</strong>
        </div>
        <div>
          <span>股票池</span>
          <strong>{{ stockUniverseText }}</strong>
        </div>
        <div>
          <span>策略数</span>
          <strong>{{ strategyCountText }}</strong>
        </div>
        <div>
          <span>特征策略</span>
          <strong>{{ featurePolicyText }}</strong>
        </div>
        <div>
          <span>ML 模型</span>
          <strong>{{ mlModeText }}</strong>
        </div>
        <div>
          <span>模拟交易</span>
          <strong>{{ paperExecutionText }}</strong>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, onMounted } from "vue";
import { api } from "../api";

const settings = reactive<Record<string, any>>({});

const versionText = computed(() => {
  const version = settings.project?.version;
  return version ? `v${version} Quantum Terminal` : "Quantum Terminal";
});
const stockUniverseText = computed(() => {
  const stock = settings.assets?.stock || {};
  return String(stock.universe || stock.label || "—");
});
const strategyCountText = computed(() => {
  const strategies = Object.values(settings.strategies || {}).filter((item: any) => item?.enabled !== false);
  return strategies.length ? `${strategies.length} active` : "—";
});
const featurePolicyText = computed(() => {
  const months = Number(settings.ml?.max_feature_age_months);
  if (settings.ml?.allow_stale_features) return "stale allowed";
  return Number.isFinite(months) && months > 0 ? `fresh ≤ ${months}m` : "fresh only";
});
const mlModeText = computed(() => settings.ml?.use_regime_models ? "LightGBM · regime-aware" : "LightGBM");
const paperExecutionText = computed(() => settings.paper_trading?.auto_execute ? "auto execute" : "manual execute");
const notificationText = computed(() => {
  const enabled = settings.trading?.notification?.enabled ? "已启用" : "已关闭";
  const changeOnly = settings.trading?.notification?.signal_change_only !== false ? "仅信号变化" : "全部信号";
  return `Telegram ${enabled} · ${changeOnly}`;
});
const sourceItems = computed(() => {
  const registry = settings.data_registry || {};
  const grouped: Record<string, { name: string; total: number; enabled: number; status: string }> = {};
  const labels: Record<string, string> = {
    akshare: "AKShare",
    tushare_free: "Tushare Free",
    tushare_mcp: "Tushare MCP",
    parquet: "Parquet",
    duckdb: "DuckDB",
  };
  for (const entry of Object.values(registry) as any[]) {
    const key = String(entry?.source || "local");
    grouped[key] = grouped[key] || { name: labels[key] || key, total: 0, enabled: 0, status: "available" };
    grouped[key].total += 1;
    if (entry?.enabled !== false) grouped[key].enabled += 1;
    if (entry?.enabled !== false && entry?.status && entry.status !== "available") grouped[key].status = String(entry.status);
  }
  return Object.values(grouped)
    .sort((a, b) => b.enabled - a.enabled || a.name.localeCompare(b.name))
    .slice(0, 6)
    .map(item => ({ ...item, summary: item.enabled ? `${item.enabled}/${item.total} dims` : "disabled" }));
});

function sourceBadgeClass(status: string): string {
  if (status === "available") return "badge-green";
  if (status === "rate_limited") return "badge-amber";
  return "badge-muted";
}

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
.settings-list .badge-muted {
  color: var(--text-disabled);
  border-color: rgba(148, 163, 184, 0.16);
  background: rgba(148, 163, 184, 0.08);
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
