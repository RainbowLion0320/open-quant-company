<template>
  <div class="view-page">
    <div class="surface-toolbar sector-toolbar">
      <div class="surface-copy">
        <span>SECTOR ROTATION</span>
        <strong>申万一级行业动量</strong>
      </div>
      <div v-if="overview" class="surface-actions">
        <span class="sector-meta-chip">
          {{ overview.total_sectors }} 行业 · {{ dataSourceLabel(overview.data_source) }}
        </span>
      </div>
    </div>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="fetchData">重试</button>
    </div>

    <!-- Summary stat chips -->
    <div v-if="overview" class="stat-row">
      <div class="stat-chip">
        <span class="stat-label">Top 5 动量</span>
        <span class="stat-value" style="color:var(--positive)">{{ top5Return }}%</span>
      </div>
      <div class="stat-chip">
        <span class="stat-label">Bottom 5 动量</span>
        <span class="stat-value" style="color:var(--negative)">{{ bottom5Return }}%</span>
      </div>
      <div class="stat-chip">
        <span class="stat-label">信号集中度</span>
        <span class="stat-value">{{ overview.signal_concentration }}</span>
      </div>
      <div class="stat-chip">
        <span class="stat-label">数据日期</span>
        <span class="stat-value" style="font-size:11px">{{ perfDate }}</span>
      </div>
    </div>

    <!-- Sector Ranking Table -->
    <div class="glass-card card-pad-lg">
      <div v-if="loading && !overview" class="empty-state empty-state-compact">
        正在加载行业快照...
      </div>
      <div v-if="sortedSectors.length" class="table-shell" style="--table-min:780px">
        <table class="data-table">
          <colgroup>
            <col style="width:8%">
            <col style="width:22%">
            <col style="width:12%">
            <col style="width:12%">
            <col style="width:12%">
            <col style="width:12%">
            <col style="width:11%">
            <col style="width:11%">
          </colgroup>
          <thead>
            <tr>
              <th>排名</th>
              <th>行业</th>
              <th class="text-right">1日</th>
              <th class="text-right">5日</th>
              <th class="text-right">20日</th>
              <th class="text-right">60日</th>
              <th class="text-right">波动率</th>
              <th class="text-right">成份股</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="s in sortedSectors"
              :key="s.sector_code"
              @click="toggleSector(s)"
              :class="{ 'row-active': activeSector === s.sector_code }"
              style="cursor:pointer"
            >
              <td class="font-mono" style="color:var(--text-disabled)">{{ s.rank }}</td>
              <td>
                <span style="color:var(--text-primary)">{{ s.sector_name }}</span>
                <span v-if="s.sector_code" class="text-2xs ml-2" style="color:var(--text-disabled)">{{ s.sector_code }}</span>
              </td>
              <td class="text-right font-mono" :style="{ color: colorPct(s.return_1d) }">{{ fmtPct(s.return_1d) }}</td>
              <td class="text-right font-mono" :style="{ color: colorPct(s.return_5d) }">{{ fmtPct(s.return_5d) }}</td>
              <td class="text-right font-mono" :style="{ color: colorPct(s.return_20d), fontWeight: '600' }">{{ fmtPct(s.return_20d) }}</td>
              <td class="text-right font-mono" :style="{ color: colorPct(s.return_60d) }">{{ fmtPct(s.return_60d) }}</td>
              <td class="text-right font-mono" style="color:var(--text-secondary)">{{ fmtPct(s.volatility) }}</td>
              <td class="text-right" style="color:var(--text-secondary)">{{ s.member_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else-if="!loading" class="empty-state">
        <span>暂无行业数据 — 运行 <code>python scripts/build_sector_snapshots.py</code> 生成快照</span>
      </div>
    </div>

    <!-- Expanded sector detail -->
    <div v-if="activeDetail" class="glass-card card-pad-lg mt-4 animate-fade-in">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-sm font-semibold" style="color:var(--text-primary)">
          {{ activeDetail.sector_name }}
          <span class="text-2xs ml-3" style="color:var(--text-disabled)">{{ activeDetail.sector_code }}</span>
        </h2>
        <button @click="activeSector = ''" class="btn btn-sm btn-ghost">收起</button>
      </div>

      <!-- Signal breakdown -->
      <div v-if="Object.keys(activeDetail.signals).length" class="mb-4">
        <h3 class="text-xs mb-2" style="color:var(--text-secondary)">策略信号分布</h3>
        <div class="signal-grid">
          <div v-for="(sig, strat) in activeDetail.signals" :key="strat" class="signal-cell">
            <div class="text-2xs mb-1" style="color:var(--text-disabled)">{{ strat }}</div>
            <div class="flex items-center gap-3">
              <span class="text-sm font-semibold" :style="{ color: sig.buy_ratio > 0.5 ? 'var(--positive)' : 'var(--text-secondary)' }">
                {{ (sig.buy_ratio * 100).toFixed(0) }}% 买入
              </span>
              <span class="text-2xs" style="color:var(--text-disabled)">
                {{ sig.buy_count }}/{{ sig.total }} · 均分 {{ sig.avg_score }}
              </span>
            </div>
            <div class="text-2xs mt-1" style="color:var(--accent)">Top: {{ sig.top_symbol || '—' }}</div>
          </div>
        </div>
      </div>

      <!-- Member stocks -->
      <div>
        <h3 class="text-xs mb-2" style="color:var(--text-secondary)">
          成份股
          <span class="text-2xs ml-2" style="color:var(--text-disabled)">{{ memberStocks.length }} / {{ memberTotal }} 只</span>
        </h3>
        <div v-if="memberStocks.length" class="member-list">
          <router-link
            v-for="s in memberStocks"
            :key="s.symbol"
            :to="`/stocks/${s.symbol}`"
            class="member-chip font-mono"
          >{{ s.symbol }}</router-link>
        </div>
        <div v-else-if="memberTotal" class="text-2xs" style="color:var(--text-disabled)">加载中...</div>
        <div v-else class="text-2xs" style="color:var(--text-disabled)">无成份股数据</div>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { api } from "../api";
import type {
  SectorOverviewResponse,
  SectorCard,
  SectorStocksResponse,
} from "../api";
import { colorBySignedRatio, fmtRatioPct as fmtPct } from "../utils/format";

const loading = ref(false);
const error = ref("");
const overview = ref<SectorOverviewResponse | null>(null);
const activeSector = ref("");
const memberStocks = ref<{ symbol: string }[]>([]);
const memberTotal = ref(0);

const sortedSectors = computed(() => {
  if (!overview.value) return [];
  return [...overview.value.sectors].sort((a, b) => a.rank - b.rank);
});

const top5Return = computed(() => {
  const top = sortedSectors.value.slice(0, 5);
  if (!top.length) return "0.00";
  const avg = top.reduce((s, x) => s + x.return_5d, 0) / top.length;
  return (avg * 100).toFixed(2);
});

const bottom5Return = computed(() => {
  const bot = sortedSectors.value.slice(-5);
  if (!bot.length) return "0.00";
  const avg = bot.reduce((s, x) => s + x.return_5d, 0) / bot.length;
  return (avg * 100).toFixed(2);
});

const perfDate = computed(() => {
  const f = overview.value?.freshness?.performance || "";
  const m = f.match(/(\d{4}-\d{2}-\d{2})|(\d{8})/);
  if (!m) return "—";
  const raw = m[1] || m[2];
  return raw.length === 8 ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6)}` : raw;
});

const activeDetail = computed(() => {
  if (!activeSector.value || !overview.value) return null;
  return overview.value.sectors.find(s => s.sector_code === activeSector.value) || null;
});

function colorPct(v: number) {
  return colorBySignedRatio(v);
}

function dataSourceLabel(source: string) {
  if (source === "real") return "真实数据";
  if (source === "proxy") return "代理数据";
  return "数据缺失";
}

async function toggleSector(s: SectorCard) {
  if (activeSector.value === s.sector_code) {
    activeSector.value = "";
    return;
  }
  activeSector.value = s.sector_code;
  memberStocks.value = [];
  memberTotal.value = 0;
  try {
    const data: SectorStocksResponse = await api.sectorStocks(s.sector_name);
    memberStocks.value = data.stocks || [];
    memberTotal.value = data.total || 0;
  } catch {}
}

async function fetchData() {
  loading.value = true;
  error.value = "";
  try {
    overview.value = await api.sectorOverview();
  } catch (e: any) {
    error.value = e?.message || "行业快照加载失败";
    overview.value = null;
  }
  loading.value = false;
}

onMounted(fetchData);
</script>

<style scoped>
.sector-toolbar {
  padding: 10px 12px;
}
.sector-toolbar .surface-copy strong {
  margin-top: 2px;
}
.sector-meta-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 9px;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: rgba(2, 6, 13, 0.28);
  color: var(--text-disabled);
  font-size: 10px;
  line-height: 1;
  white-space: nowrap;
}
.stat-row {
  display: flex;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.stat-chip {
  background: rgba(0, 212, 255, 0.04);
  border: 1px solid rgba(0, 212, 255, 0.08);
  border-radius: 6px;
  padding: 8px 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.stat-label {
  font-size: 10px;
  color: var(--text-disabled);
  text-transform: uppercase;
}
.stat-value {
  font-size: 15px;
  font-weight: 600;
  font-family: "JetBrains Mono", monospace;
  color: var(--text-primary);
}
.row-active {
  background: rgba(0, 212, 255, 0.06) !important;
}
.signal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 8px;
}
.signal-cell {
  background: rgba(0, 212, 255, 0.03);
  border: 1px solid rgba(0, 212, 255, 0.06);
  border-radius: 6px;
  padding: 10px 14px;
}
.member-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.member-chip {
  font-size: 11px;
  padding: 3px 10px;
  background: rgba(0, 212, 255, 0.05);
  border: 1px solid rgba(0, 212, 255, 0.1);
  border-radius: 4px;
  color: var(--accent);
  text-decoration: none;
  transition: background 0.2s;
}
.member-chip:hover {
  background: rgba(0, 212, 255, 0.12);
}
</style>
