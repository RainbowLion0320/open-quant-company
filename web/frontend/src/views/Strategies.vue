<template>
  <div class="view-page">
    <div class="surface-toolbar">
      <div class="surface-copy">
        <span>STRATEGY REGISTRY</span>
        <strong>四策略扫描状态</strong>
        <small>运行策略、查看生命周期状态，并展开最新候选信号</small>
      </div>
      <div class="surface-actions">
        <span v-if="loaded && store.strategies.length" class="text-2xs" style="color:var(--text-disabled)">{{ store.strategies.length }} strategies</span>
        <button @click="runAll" :disabled="store.running" class="btn btn-primary btn-sm">
          {{ store.running ? `运行中 ${store.progress}%` : '运行全部' }}
        </button>
      </div>
    </div>

    <div v-if="store.error" class="inline-alert danger">
      <span>{{ store.error }}</span>
      <button class="btn btn-xs" @click="reload">重试</button>
    </div>

    <!-- Progress Bar -->
    <div v-if="store.running" class="glass-card card-pad">
      <div class="text-xs mb-2" style="color:var(--text-secondary)">{{ store.progressMsg }}</div>
      <div class="progress-bar">
        <div class="progress-bar-fill" :style="{ width: store.progress + '%' }"></div>
      </div>
    </div>

    <div v-if="store.loading && !loaded" class="glass-card card-pad-lg empty-panel">
      正在加载策略注册表...
    </div>

    <div v-if="loaded && !store.strategies.length && !store.running" class="glass-card card-pad-lg empty-panel">
      暂无策略扫描结果
    </div>

    <div v-if="governance" class="governance-panel glass-card">
      <div class="governance-header">
        <div>
          <span>RESEARCH STACK</span>
          <strong>策略研究分层</strong>
        </div>
        <div class="gate-chip">Paper gate: Sharpe ≥ {{ paperGateSharpe }} · MaxDD ≤ {{ paperGateDrawdown }}%</div>
      </div>
      <div class="role-grid">
        <div v-for="role in governance.roles" :key="role.name" class="role-card">
          <div class="role-title">
            <span :style="{ background: colorFor(role.name) }"></span>
            <strong>{{ labelFor(role.name) }}</strong>
          </div>
          <div class="role-layer">{{ layerLabel(role.layer) }}</div>
          <p>{{ role.primary_use }}</p>
        </div>
      </div>
    </div>

    <!-- Strategy Cards -->
    <div v-for="s in store.strategies" :key="s.name" class="strategy-card glass-card glow-cyan animate-fade-in">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center gap-3">
          <div class="w-2 h-2 rounded-full" :style="{ background: colorFor(s.name), boxShadow: `0 0 6px ${colorFor(s.name)}` }"></div>
          <div>
            <h2 class="text-sm font-semibold" style="color:var(--text-primary)">
              {{ s.label }}
              <span :class="['status-badge', `status-${statusFor(s.name)}`]">{{ statusLabelFor(s.name) }}</span>
            </h2>
            <div class="text-[11px] mt-0.5" style="color:var(--text-disabled)">
              {{ s.total }} 只扫描 · {{ s.buys }} 只买入
              <span v-if="s.last_computed" class="ml-3">updated {{ s.last_computed?.slice(0, 16) }}</span>
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
        <div class="table-shell" style="--table-min:680px">
          <table class="data-table">
            <colgroup>
              <col style="width:14%">
              <col style="width:22%">
              <col style="width:22%">
              <col style="width:18%">
              <col style="width:24%">
            </colgroup>
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
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { useStrategyStore } from "../stores";
import { api, type StrategyGovernanceResponse } from "../api";

const store = useStrategyStore();
const currentStrategy = ref("");
const signals = ref<any[]>([]);
const loaded = ref(false);
const strategyStatuses = ref<Record<string, string>>({});
const governance = ref<StrategyGovernanceResponse | null>(null);

const STATUS_LABELS: Record<string, string> = {
  candidate: "候选",
  validated: "已验证",
  paper: "模拟盘",
  production: "生产",
  retired: "已退役",
};

function statusFor(name: string) { return strategyStatuses.value[name] || "candidate"; }
function statusLabelFor(name: string) { return STATUS_LABELS[statusFor(name)] || statusFor(name); }

const strategyColors: Record<string, string> = {
  buffett: "#00d4ff",
  multifactor: "#22c55e",
  cybernetic: "#eab308",
  ml_lgbm: "#7c3aed",
};
function colorFor(name: string) { return strategyColors[name] || "var(--accent)"; }
function labelFor(name: string) {
  return store.strategies.find(s => s.name === name)?.label || name;
}
function layerLabel(layer: string) {
  return {
    quality_filter: "质量过滤层",
    primary_alpha: "主 Alpha",
    auxiliary_alpha: "辅助 Alpha",
    risk_overlay: "风险覆盖层",
  }[layer] || layer;
}

const paperGateSharpe = computed(() => governance.value?.promotion_rules?.paper?.min_sharpe?.toFixed(2) || "0.50");
const paperGateDrawdown = computed(() => {
  const v = governance.value?.promotion_rules?.paper?.max_drawdown ?? 0.25;
  return Math.round(v * 100);
});

async function toggleSignals(name: string) {
  if (currentStrategy.value === name) { currentStrategy.value = ""; signals.value = []; return; }
  currentStrategy.value = name;
  await store.fetchSignals(name);
  signals.value = store.signals[name] || [];
}

function runAll() { store.run("all"); }
function runSingle(name: string) { store.run(name); }

async function reload() {
  loaded.value = false;
  try { await Promise.all([store.fetchList(), loadStatuses(), loadGovernance()]); }
  finally { loaded.value = true; }
}

async function loadStatuses() {
  try {
    const data = await api.strategyStatuses();
    const map: Record<string, string> = {};
    for (const s of data.strategies) {
      map[s.name] = s.status;
    }
    strategyStatuses.value = map;
  } catch {}
}

async function loadGovernance() {
  try {
    governance.value = await api.strategyGovernance();
  } catch {
    governance.value = null;
  }
}

onMounted(reload);
</script>

<style scoped>
.strategy-card {
  padding: 16px;
}
.governance-panel {
  padding: 14px;
}
.governance-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.governance-header span {
  display: block;
  color: var(--text-disabled);
  font-size: 10px;
  letter-spacing: 0;
}
.governance-header strong {
  color: var(--text-primary);
  font-size: 13px;
}
.gate-chip {
  border: 1px solid rgba(0, 212, 255, 0.18);
  color: var(--text-secondary);
  font-size: 11px;
  padding: 5px 8px;
}
.role-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.role-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  padding: 10px;
  min-height: 96px;
}
.role-title {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  font-size: 12px;
}
.role-title span {
  width: 7px;
  height: 7px;
  border-radius: 999px;
}
.role-layer {
  margin-top: 8px;
  color: var(--accent);
  font-size: 11px;
}
.role-card p {
  margin-top: 6px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.45;
}
.empty-panel {
  min-height: 120px;
  display: grid;
  place-items: center;
  color: var(--text-disabled);
  font-size: 12px;
}
@media (max-width: 760px) {
  .governance-header {
    align-items: flex-start;
    flex-direction: column;
  }
  .role-grid {
    grid-template-columns: 1fr;
  }
  .strategy-card > div:first-child {
    align-items: flex-start;
    flex-direction: column;
  }
  .strategy-card > div:first-child > .flex:last-child {
    width: 100%;
  }
  .strategy-card button {
    flex: 1;
    justify-content: center;
  }
}
</style>
