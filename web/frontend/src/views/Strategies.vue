<template>
  <div class="view-page">
    <div class="surface-toolbar">
      <div class="surface-copy">
        <span>STRATEGY CATALOG</span>
        <strong>策略目录</strong>
        <small>统一查看生产策略、候选策略、研究证据和最新扫描状态</small>
      </div>
      <div class="surface-actions">
        <span v-if="loaded" class="text-2xs" style="color:var(--text-disabled)">{{ catalog.length }} strategies</span>
        <button @click="runAll" :disabled="store.running" class="btn btn-primary btn-sm">
          {{ store.running ? `运行中 ${store.progress}%` : '运行生产策略' }}
        </button>
      </div>
    </div>

    <div class="isolation-banner">
      <strong>生产隔离</strong>
      <span>生产隔离：candidate/validated 只允许研究扫描和回测，不参与生产信号</span>
    </div>

    <div v-if="store.error" class="inline-alert danger">
      <span>{{ store.error }}</span>
      <button class="btn btn-xs" @click="reload">重试</button>
    </div>

    <div v-if="store.running" class="glass-card card-pad">
      <div class="text-xs mb-2" style="color:var(--text-secondary)">{{ store.progressMsg }}</div>
      <div class="progress-bar">
        <div class="progress-bar-fill" :style="{ width: store.progress + '%' }"></div>
      </div>
    </div>

    <div class="catalog-stats">
      <div v-for="card in statusCards" :key="card.key" class="glass-card catalog-stat">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </div>
    </div>

    <div class="catalog-controls glass-card">
      <label>
        <span>生命周期</span>
        <select v-model="filters.lifecycle">
          <option value="">全部</option>
          <option v-for="item in lifecycleOptions" :key="item" :value="item">{{ lifecycleLabel(item) }}</option>
        </select>
      </label>
      <label>
        <span>策略类型</span>
        <select v-model="filters.strategyType">
          <option value="">全部</option>
          <option v-for="item in typeOptions" :key="item" :value="item">{{ typeLabel(item) }}</option>
        </select>
      </label>
      <label>
        <span>研究层级</span>
        <select v-model="filters.layer">
          <option value="">全部</option>
          <option v-for="item in layerOptions" :key="item" :value="item">{{ layerLabel(item) }}</option>
        </select>
      </label>
      <div class="evaluation-note">
        <span>候选策略晋级需覆盖 {{ evaluation?.baselines.length || 0 }} 个强基准</span>
        <small>{{ evaluation?.status || 'research_required' }}</small>
      </div>
    </div>

    <div v-if="store.loading && !loaded" class="glass-card card-pad-lg empty-panel">
      正在加载策略目录...
    </div>

    <div v-if="loaded && !filteredCatalog.length" class="glass-card card-pad-lg empty-panel">
      当前筛选条件下没有策略
    </div>

    <div v-if="filteredCatalog.length" class="table-shell catalog-table-shell" style="--table-min:960px">
      <table class="data-table catalog-table">
        <colgroup>
          <col style="width:20%">
          <col style="width:12%">
          <col style="width:13%">
          <col style="width:14%">
          <col style="width:18%">
          <col style="width:12%">
          <col style="width:11%">
        </colgroup>
        <thead>
          <tr>
            <th>策略</th>
            <th>生命周期</th>
            <th>类型</th>
            <th>层级</th>
            <th>数据需求</th>
            <th class="text-right">最新扫描</th>
            <th class="text-right">动作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="item in filteredCatalog" :key="item.name">
            <tr>
              <td>
                <div class="strategy-cell">
                  <span class="strategy-dot" :style="{ background: colorFor(item.name), boxShadow: `0 0 8px ${colorFor(item.name)}` }"></span>
                  <div>
                    <strong>{{ item.label }}</strong>
                    <small>{{ item.name }}</small>
                  </div>
                </div>
              </td>
              <td><span :class="['status-badge', `status-${item.lifecycle}`]">{{ lifecycleLabel(item.lifecycle) }}</span></td>
              <td>{{ typeLabel(item.strategy_type) }}</td>
              <td>{{ layerLabel(item.layer) }}</td>
              <td>
                <div class="requirement-list">
                  <span v-for="req in item.data_requirements" :key="`${item.name}-${req}`">{{ req }}</span>
                </div>
              </td>
              <td class="text-right">
                <span class="scan-meta">{{ scanMeta(item.name) }}</span>
              </td>
              <td class="text-right">
                <div class="row-actions">
                  <button @click="toggleSignals(item.name)" class="btn btn-xs btn-ghost">信号</button>
                  <button @click="runCatalogStrategy(item)" :disabled="store.running" class="btn btn-xs">
                    {{ item.lifecycle === 'production' ? '运行' : '研究扫描' }}
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="currentStrategy === item.name" class="signal-row">
              <td colspan="7">
                <div v-if="signals.length" class="signal-preview">
                  <div v-for="sig in signals.slice(0, 10)" :key="`${item.name}-${sig.symbol}`" class="signal-chip">
                    <router-link :to="`/stocks/${sig.symbol}`">{{ sig.symbol }}</router-link>
                    <span>{{ sig.name }}</span>
                    <strong>{{ sig.score?.toFixed(1) }}</strong>
                    <em>{{ signalLabel(sig.signal) }}</em>
                  </div>
                </div>
                <div v-else class="signal-empty">暂无已保存信号，先执行扫描后查看。</div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
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
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { useStrategyStore } from "../stores";
import {
  api,
  type StrategyCatalogItem,
  type StrategyEvaluationSummary,
  type StrategyGovernanceResponse,
} from "../api";

const store = useStrategyStore();
const currentStrategy = ref("");
const signals = ref<any[]>([]);
const loaded = ref(false);
const catalog = ref<StrategyCatalogItem[]>([]);
const governance = ref<StrategyGovernanceResponse | null>(null);
const evaluation = ref<StrategyEvaluationSummary | null>(null);
const filters = ref({ lifecycle: "", strategyType: "", layer: "" });

const STATUS_LABELS: Record<string, string> = {
  candidate: "候选",
  validated: "已验证",
  paper: "模拟盘",
  production: "生产",
  retired: "已退役",
};

const TYPE_LABELS: Record<string, string> = {
  selection: "选股",
  timing: "择时",
  sector_rotation: "行业轮动",
  portfolio: "组合",
  risk_overlay: "风险覆盖",
};

const LAYER_LABELS: Record<string, string> = {
  quality_filter: "质量过滤层",
  primary_alpha: "主 Alpha",
  auxiliary_alpha: "辅助 Alpha",
  candidate_alpha: "候选 Alpha",
  defensive_alpha: "防御 Alpha",
  confirmation_alpha: "确认 Alpha",
  risk_overlay: "风险覆盖层",
};

const strategyColors: Record<string, string> = {
  buffett: "#00d4ff",
  multifactor: "#22c55e",
  cybernetic: "#eab308",
  ml_lgbm: "#7c3aed",
  trend_following: "#38bdf8",
  donchian_breakout: "#f97316",
  rps_relative_strength: "#22c55e",
  sector_rotation: "#06b6d4",
  quality_value: "#84cc16",
  low_vol_defensive: "#a78bfa",
  volume_confirmation: "#facc15",
  regime_gated: "#fb7185",
};

const scanByName = computed(() => {
  const map: Record<string, any> = {};
  for (const item of store.strategies) map[item.name] = item;
  return map;
});

const filteredCatalog = computed(() => catalog.value.filter(item => {
  if (filters.value.lifecycle && item.lifecycle !== filters.value.lifecycle) return false;
  if (filters.value.strategyType && item.strategy_type !== filters.value.strategyType) return false;
  if (filters.value.layer && item.layer !== filters.value.layer) return false;
  return true;
}));

const lifecycleOptions = computed(() => [...new Set(catalog.value.map(item => item.lifecycle))]);
const typeOptions = computed(() => [...new Set(catalog.value.map(item => item.strategy_type))]);
const layerOptions = computed(() => [...new Set(catalog.value.map(item => item.layer))]);
const statusCards = computed(() => {
  const count = (status: string) => catalog.value.filter(item => item.lifecycle === status).length;
  return [
    { key: "total", label: "全部策略", value: catalog.value.length },
    { key: "production", label: "生产", value: count("production") },
    { key: "paper", label: "模拟盘", value: count("paper") },
    { key: "candidate", label: "候选策略", value: count("candidate") },
  ];
});

const paperGateSharpe = computed(() => governance.value?.promotion_rules?.paper?.min_sharpe?.toFixed(2) || "0.50");
const paperGateDrawdown = computed(() => {
  const v = governance.value?.promotion_rules?.paper?.max_drawdown ?? 0.25;
  return Math.round(v * 100);
});

function lifecycleLabel(status: string) { return STATUS_LABELS[status] || status; }
function typeLabel(type: string) { return TYPE_LABELS[type] || type; }
function layerLabel(layer: string) { return LAYER_LABELS[layer] || layer; }
function colorFor(name: string) { return strategyColors[name] || "var(--accent)"; }
function labelFor(name: string) {
  return catalog.value.find(s => s.name === name)?.label || name;
}
function signalLabel(signal: string) {
  return signal === "buy" ? "买入" : signal === "sell" ? "卖出" : "持有";
}
function scanMeta(name: string) {
  const meta = scanByName.value[name];
  if (!meta) return "未扫描";
  const when = meta.last_computed ? meta.last_computed.slice(0, 16) : "";
  return `${meta.total || 0}只 / ${meta.buys || 0}买入${when ? ` · ${when}` : ""}`;
}

async function toggleSignals(name: string) {
  if (currentStrategy.value === name) { currentStrategy.value = ""; signals.value = []; return; }
  currentStrategy.value = name;
  await store.fetchSignals(name);
  signals.value = store.signals[name] || [];
}

function runAll() {
  store.run("all", 0, undefined, "production");
}
function runCatalogStrategy(item: StrategyCatalogItem) {
  const mode = item.lifecycle === "production" ? "production" : "research";
  const limit = item.lifecycle === "production" ? 0 : 200;
  store.run(item.name, limit, undefined, mode);
}

async function reload() {
  loaded.value = false;
  try {
    await Promise.all([store.fetchList(), loadCatalog(), loadGovernance(), loadEvaluation()]);
  } finally {
    loaded.value = true;
  }
}

async function loadCatalog() {
  const data = await api.strategyCatalog();
  catalog.value = data.items || [];
}

async function loadGovernance() {
  try {
    governance.value = await api.strategyGovernance();
  } catch {
    governance.value = null;
  }
}

async function loadEvaluation() {
  try {
    evaluation.value = await api.strategyEvaluation();
  } catch {
    evaluation.value = null;
  }
}

onMounted(reload);
</script>

<style scoped>
.isolation-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid rgba(251, 113, 133, 0.26);
  background: rgba(251, 113, 133, 0.07);
  padding: 9px 12px;
  color: var(--text-secondary);
  font-size: 12px;
}
.isolation-banner strong {
  color: #fb7185;
  font-size: 11px;
  text-transform: uppercase;
}
.catalog-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.catalog-stat {
  padding: 12px;
}
.catalog-stat span {
  display: block;
  color: var(--text-disabled);
  font-size: 11px;
}
.catalog-stat strong {
  display: block;
  margin-top: 4px;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 22px;
}
.catalog-controls {
  display: grid;
  grid-template-columns: repeat(3, minmax(120px, 180px)) minmax(220px, 1fr);
  align-items: end;
  gap: 12px;
  padding: 12px;
}
.catalog-controls label {
  display: grid;
  gap: 5px;
}
.catalog-controls label span {
  color: var(--text-disabled);
  font-size: 10px;
}
.catalog-controls select {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(2, 6, 23, 0.75);
  color: var(--text-primary);
  font-size: 12px;
  padding: 7px 8px;
  outline: none;
}
.evaluation-note {
  justify-self: end;
  text-align: right;
  color: var(--text-secondary);
  font-size: 12px;
}
.evaluation-note small {
  display: block;
  color: var(--text-disabled);
  font-size: 10px;
  margin-top: 3px;
}
.catalog-table-shell {
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.strategy-cell {
  display: flex;
  align-items: center;
  gap: 9px;
}
.strategy-cell strong {
  display: block;
  color: var(--text-primary);
  font-size: 12px;
}
.strategy-cell small {
  display: block;
  color: var(--text-disabled);
  font-size: 10px;
  margin-top: 2px;
}
.strategy-dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  flex: 0 0 auto;
}
.requirement-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.requirement-list span {
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: var(--text-secondary);
  font-size: 10px;
  padding: 2px 5px;
}
.scan-meta {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 11px;
}
.row-actions {
  display: inline-flex;
  justify-content: flex-end;
  gap: 6px;
}
.signal-row td {
  background: rgba(255, 255, 255, 0.025);
}
.signal-preview {
  display: grid;
  grid-template-columns: repeat(5, minmax(120px, 1fr));
  gap: 6px;
  padding: 8px 0;
}
.signal-chip {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  gap: 6px;
  align-items: center;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(2, 6, 23, 0.45);
  padding: 5px 6px;
  font-size: 10px;
}
.signal-chip a {
  color: var(--accent);
  font-family: var(--font-mono);
}
.signal-chip span {
  min-width: 0;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.signal-chip strong {
  color: var(--text-primary);
  font-family: var(--font-mono);
}
.signal-chip em {
  color: var(--text-disabled);
  font-style: normal;
}
.signal-empty {
  padding: 8px 0;
  color: var(--text-disabled);
  font-size: 12px;
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
@media (max-width: 980px) {
  .catalog-stats,
  .catalog-controls,
  .role-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .evaluation-note {
    justify-self: start;
    text-align: left;
  }
  .signal-preview {
    grid-template-columns: repeat(2, minmax(120px, 1fr));
  }
}
@media (max-width: 640px) {
  .catalog-stats,
  .catalog-controls,
  .role-grid,
  .signal-preview {
    grid-template-columns: 1fr;
  }
  .isolation-banner {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }
}
</style>
