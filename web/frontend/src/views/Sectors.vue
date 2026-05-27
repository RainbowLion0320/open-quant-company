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

    <section v-if="overview" class="sector-radar-layout">
      <div class="glass-card sector-map-card">
        <div class="sector-map-head">
          <div>
            <span>INDUSTRY CAPITAL MAP</span>
            <strong>行业资金方块图</strong>
          </div>
          <div class="block-mode-tabs" role="tablist" aria-label="行业热力模式">
            <button
              v-for="mode in blockHeatModes"
              :key="mode.key"
              type="button"
              :class="{ active: blockHeatMode === mode.key }"
              @click="blockHeatMode = mode.key"
            >{{ mode.label }}</button>
          </div>
        </div>
        <div class="block-map-meta">
          <span>面积: {{ blockSizeLabel }}</span>
          <span>颜色: {{ activeBlockHeatMode?.metric }}</span>
          <span>资金口径: {{ capitalSourceLabel }}</span>
        </div>
        <div v-if="sectorBlockTiles.length" class="sector-block-grid" role="img" aria-label="申万一级行业独立方块矩阵">
          <article
            v-for="tile in sectorBlockTiles"
            :key="tile.sector.sector_code"
            class="industry-block"
            :class="[
              `span-${tile.span}`,
              { active: activeSector === tile.sector.sector_code, 'is-compact': tile.span === 1 },
            ]"
            :style="industryBlockStyle(tile)"
            :title="industryTitle(tile)"
          >
            <button
              type="button"
              class="industry-block-button"
              @click="toggleSector(tile.sector)"
            >
              <span class="industry-name-row">
                <span class="industry-name">{{ tile.sector.sector_name }}</span>
                <strong>{{ formatAmount(tile.size) }}</strong>
              </span>
              <span class="industry-metric">{{ tile.metricLabel }}</span>
              <span class="industry-code">{{ tile.sector.sector_code || 'SW1' }}</span>
            </button>
          </article>
        </div>
        <div v-else class="empty-state empty-state-compact">暂无可绘制的行业资金数据</div>
      </div>

      <aside class="glass-card sector-insight-card">
        <div>
          <span class="insight-label">资金最大行业</span>
          <strong>{{ capitalLeader?.sector_name || '—' }}</strong>
          <em>{{ capitalLeader ? formatAmount(tileSize(capitalLeader)) : '—' }}</em>
        </div>
        <div>
          <span class="insight-label">资金集中度</span>
          <strong>{{ capitalConcentration }}</strong>
          <em>Top 5 成交占比</em>
        </div>
        <div>
          <span class="insight-label">当前热力</span>
          <strong>{{ activeBlockHeatMode?.label || '—' }}</strong>
          <em>{{ activeBlockHeatMode?.metric || '—' }}</em>
        </div>
      </aside>
    </section>

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

    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { api } from "../api";
import type {
  SectorOverviewResponse,
  SectorCard,
} from "../api";
import { colorBySignedRatio, fmtRatioPct as fmtPct } from "../utils/format";

const loading = ref(false);
const error = ref("");
const overview = ref<SectorOverviewResponse | null>(null);
const activeSector = ref("");
type BlockHeatMode = "capital" | "momentum" | "signal";

const blockHeatMode = ref<BlockHeatMode>("capital");
const blockHeatModes: { key: BlockHeatMode; label: string; metric: string }[] = [
  { key: "capital", label: "资金热力", metric: "5日涨跌幅" },
  { key: "momentum", label: "动量热力", metric: "20日涨跌幅" },
  { key: "signal", label: "信号热力", metric: "策略买入集中度" },
];

type SectorBlockTile = {
  sector: SectorCard;
  size: number;
  span: number;
  metric: number;
  metricLabel: string;
};

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

const activeBlockHeatMode = computed(() => blockHeatModes.find(m => m.key === blockHeatMode.value));

const capitalSourceLabel = computed(() => dataSourceLabel(overview.value?.capital_source || "missing"));

const blockSizeLabel = computed(() => (
  sortedSectors.value.some(s => Number(s.amount_5d_avg || 0) > 0)
    ? "近5日平均成交额"
    : "成份股数量 fallback"
));

const capitalLeader = computed(() => {
  const sectors = [...sortedSectors.value].sort((a, b) => tileSize(b) - tileSize(a));
  return sectors[0] || null;
});

const capitalConcentration = computed(() => {
  const sectors = [...sortedSectors.value].sort((a, b) => tileSize(b) - tileSize(a));
  const total = sectors.reduce((sum, sector) => sum + tileSize(sector), 0);
  if (!total) return "—";
  const top5 = sectors.slice(0, 5).reduce((sum, sector) => sum + tileSize(sector), 0);
  return `${((top5 / total) * 100).toFixed(1)}%`;
});

const sectorBlockTiles = computed<SectorBlockTile[]>(() => {
  const items = sortedSectors.value
    .map(sector => ({ sector, size: tileSize(sector) }))
    .filter(item => item.size > 0)
    .sort((a, b) => b.size - a.size);
  const maxSize = items[0]?.size || 1;
  return items.map(item => {
    const span = sectorBlockSpan(item.size, maxSize);
    return {
      ...item,
      span,
      metric: blockMetric(item.sector),
      metricLabel: blockMetricLabel(item.sector),
    };
  });
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

function signalPower(sector: SectorCard) {
  const ratios = Object.values(sector.signals || {}).map(signal => Number(signal.buy_ratio || 0));
  return ratios.length ? Math.max(...ratios) : 0;
}

function tileSize(sector: SectorCard) {
  const amount = Number(sector.amount_5d_avg || sector.turnover_amount || 0);
  if (amount > 0) return amount;
  return Math.max(Number(sector.member_count || 0), 1);
}

function blockMetric(sector: SectorCard) {
  if (blockHeatMode.value === "momentum") return Number(sector.return_20d || 0);
  if (blockHeatMode.value === "signal") return signalPower(sector) - 0.5;
  return Number(sector.return_5d || 0);
}

function blockMetricLabel(sector: SectorCard) {
  if (blockHeatMode.value === "signal") return `${(signalPower(sector) * 100).toFixed(0)}% buy`;
  return fmtPct(blockHeatMode.value === "momentum" ? sector.return_20d : sector.return_5d);
}

function formatAmount(value: number) {
  const n = Number(value || 0);
  if (n >= 100_000_000) return `${(n / 100_000_000).toFixed(1)}亿`;
  if (n >= 10_000) return `${(n / 10_000).toFixed(1)}万`;
  return n.toFixed(0);
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function sectorBlockSpan(size: number, maxSize: number) {
  if (maxSize <= 0) return 1;
  const ratio = clampNumber(size / maxSize, 0, 1);
  return clampNumber(Math.ceil(Math.sqrt(ratio) * 4 - 0.15), 1, 4);
}

function industryTitle(tile: SectorBlockTile) {
  return `${tile.sector.sector_name} · ${blockSizeLabel.value} ${formatAmount(tile.size)} · ${activeBlockHeatMode.value?.metric}: ${tile.metricLabel}`;
}

function heatStyle(metric: number) {
  const abs = Math.min(Math.abs(metric) * 7, 0.48);
  if (metric > 0) {
    return {
      backgroundColor: `rgba(21, 128, 61, ${0.18 + abs})`,
      border: `rgba(34, 197, 94, ${0.24 + abs * 0.72})`,
      boxShadow: `inset 0 0 0 1px rgba(187, 247, 208, ${0.04 + abs * 0.14}), inset 0 -28px 68px rgba(2, 6, 13, 0.18)`,
      color: "var(--positive)",
    };
  }
  if (metric < 0) {
    return {
      backgroundColor: `rgba(153, 27, 27, ${0.18 + abs})`,
      border: `rgba(248, 113, 113, ${0.24 + abs * 0.72})`,
      boxShadow: `inset 0 0 0 1px rgba(254, 202, 202, ${0.04 + abs * 0.14}), inset 0 -28px 68px rgba(2, 6, 13, 0.18)`,
      color: "var(--negative)",
    };
  }
  return {
    backgroundColor: "rgba(15, 23, 42, 0.72)",
    border: "rgba(125, 211, 252, 0.18)",
    boxShadow: "inset 0 0 0 1px rgba(125, 211, 252, 0.04), inset 0 -28px 68px rgba(2, 6, 13, 0.16)",
    color: "var(--text-secondary)",
  };
}

function industryBlockStyle(tile: SectorBlockTile) {
  const tone = heatStyle(tile.metric);
  return {
    gridColumn: `span ${tile.span}`,
    gridRow: `span ${tile.span}`,
    backgroundColor: tone.backgroundColor,
    borderColor: activeSector.value === tile.sector.sector_code ? "var(--accent)" : tone.border,
    boxShadow: tone.boxShadow,
    color: tone.color,
  };
}

function dataSourceLabel(source: string) {
  if (source === "real") return "真实数据";
  if (source === "proxy") return "代理数据";
  if (source === "estimated") return "估算数据";
  return "数据缺失";
}

function toggleSector(s: SectorCard) {
  if (activeSector.value === s.sector_code) {
    activeSector.value = "";
    return;
  }
  activeSector.value = s.sector_code;
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
.sector-radar-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 12px;
  margin-bottom: 14px;
}
.sector-map-card,
.sector-insight-card {
  padding: 12px;
}
.sector-map-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}
.sector-map-head span,
.insight-label {
  display: block;
  color: var(--text-disabled);
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.sector-map-head strong {
  display: block;
  margin-top: 3px;
  color: var(--text-primary);
  font-size: 15px;
}
.block-mode-tabs {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: rgba(2, 6, 13, 0.32);
}
.block-mode-tabs button {
  min-height: 24px;
  padding: 0 9px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--text-disabled);
  font-size: 10px;
  cursor: pointer;
}
.block-mode-tabs button.active {
  background: rgba(0, 212, 255, 0.10);
  color: var(--accent);
}
.block-map-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 10px 0;
}
.block-map-meta span {
  min-height: 22px;
  padding: 0 8px;
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  color: var(--text-disabled);
  font-size: 10px;
}
.sector-block-grid {
  --block-cell: 78px;
  --block-gap: 10px;
  display: grid;
  grid-template-columns: repeat(auto-fill, var(--block-cell));
  grid-auto-rows: var(--block-cell);
  grid-auto-flow: dense;
  gap: var(--block-gap);
  align-items: stretch;
  justify-content: start;
}
.industry-block {
  min-height: 0;
  border: 1px solid;
  border-radius: 7px;
  overflow: hidden;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
  transition: border-color 0.18s ease, filter 0.18s ease, transform 0.18s ease;
}
.industry-block:hover,
.industry-block.active {
  filter: brightness(1.14);
}
.industry-block.active {
  box-shadow: inset 0 0 0 1px rgba(0, 212, 255, 0.45), 0 0 18px rgba(0, 212, 255, 0.16);
}
.industry-block-button {
  width: 100%;
  height: 100%;
  min-width: 0;
  padding: 9px;
  display: grid;
  grid-template-rows: auto 1fr auto;
  align-items: start;
  gap: 8px;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}
.industry-name-row {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: start;
}
.industry-name {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 800;
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.industry-name-row strong {
  color: currentColor;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  line-height: 1.15;
  white-space: nowrap;
}
.industry-metric {
  align-self: center;
  color: currentColor;
  font-family: "JetBrains Mono", monospace;
  font-size: clamp(14px, calc(var(--block-cell) / 4), 28px);
  font-weight: 800;
  line-height: 1;
  letter-spacing: 0;
}
.industry-code {
  align-self: end;
  color: var(--text-secondary);
  font-size: 10px;
  line-height: 1.1;
}
.industry-block.span-1 .industry-metric,
.industry-block.span-1 .industry-code {
  display: none;
}
.industry-block.span-1 .industry-block-button {
  padding: 7px;
}
.industry-block.span-1 .industry-name-row {
  grid-template-columns: 1fr;
  gap: 2px;
}
.sector-insight-card {
  display: grid;
  grid-template-rows: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.sector-insight-card > div {
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(0, 212, 255, 0.035);
}
.sector-insight-card strong {
  display: block;
  margin-top: 8px;
  color: var(--text-primary);
  font-size: 17px;
}
.sector-insight-card em {
  display: block;
  margin-top: 3px;
  color: var(--text-disabled);
  font-size: 10px;
  font-style: normal;
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
@media (max-width: 980px) {
  .sector-radar-layout {
    grid-template-columns: 1fr;
  }
  .sector-insight-card {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    grid-template-rows: none;
  }
}
@media (max-width: 640px) {
  .sector-map-head {
    flex-direction: column;
  }
  .block-mode-tabs {
    width: 100%;
  }
  .block-mode-tabs button {
    flex: 1;
    padding: 0 5px;
  }
  .sector-block-grid {
    --block-cell: 72px;
    --block-gap: 8px;
  }
  .sector-insight-card {
    grid-template-columns: 1fr;
  }
}
</style>
