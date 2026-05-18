<template>
  <div class="db-health view-page">
    <!-- Hero summary -->
    <section class="health-hero">
      <article class="telemetry-card glass-card">
        <div class="metric-head"><span>逻辑表</span></div>
        <div class="metric-main">
          <strong style="color:var(--accent)">{{ summary?.tables ?? '—' }}</strong>
          <span>张表</span>
        </div>
      </article>

      <article class="telemetry-card glass-card">
        <div class="metric-head"><span>数据量</span></div>
        <div class="metric-main">
          <strong style="color:var(--positive)">{{ fmtSize(summary?.total_size_mb) }}</strong>
          <span>总计</span>
        </div>
      </article>

      <article class="telemetry-card glass-card">
        <div class="metric-head"><span>缺失值</span></div>
        <div class="metric-main">
          <strong :style="{ color: missingColor }">{{ fmtPercent(summary?.avg_missing_pct) }}</strong>
          <span>平均</span>
        </div>
      </article>

      <article class="telemetry-card glass-card">
        <div class="metric-head"><span>异常值</span></div>
        <div class="metric-main">
          <strong :style="{ color: outlierColor }">{{ fmtCount(summary?.total_outliers) }}</strong>
          <span>总计 (IQR×3)</span>
        </div>
      </article>
    </section>

    <!-- Status bar -->
    <div class="status-bar">
      <span class="status-dot" :class="statusClass"></span>
      <span v-if="statusText">{{ statusText }}</span>
      <span v-if="summary?.checked_at" class="checked-at">
        上次检查: {{ fmtTime(summary.checked_at) }}
      </span>
    </div>

    <!-- Table -->
    <div class="table-wrap glass-card">
      <table>
        <thead>
          <tr>
            <th>表名</th>
            <th>数据源</th>
            <th class="num">行数</th>
            <th class="num">列数</th>
            <th class="num">文件数</th>
            <th class="num">大小</th>
            <th class="num">缺失%</th>
            <th class="num">异常值</th>
            <th class="num">新鲜度</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(row, i) in rows" :key="i">
            <tr :class="{ 'row-error': row.error }">
              <td class="table-name">
                <span class="name-text" :title="row.label_zh || undefined">{{ row.table }}</span>
                <span v-if="row.error" class="error-badge" :title="row.error">⚠</span>
              </td>
              <td class="source-cell">{{ row.source || '—' }}</td>
              <td class="num">{{ fmtCount(row.rows) }}</td>
              <td class="num">{{ row.columns }}</td>
              <td class="num">{{ row.files || 1 }}</td>
              <td class="num mono">{{ fmtSize(row.size_mb) }}</td>
              <td class="num">
                <span :class="missingClass(row.missing_pct)">
                  {{ row.missing_pct?.toFixed(1) ?? '—' }}%
                </span>
              </td>
              <td class="num">
                <span :class="outlierClass(row.outlier_count)">
                  {{ fmtCount(row.outlier_count) }}
                </span>
              </td>
              <td class="num">
                <span :class="freshnessClass(row.freshness_days)">
                  {{ freshnessLabel(row.freshness_days) }}
                </span>
              </td>
              <td class="detail-cell">
                <button
                  v-if="hasDetail(row)"
                  class="detail-btn"
                  @click="toggleDetail(i)"
                >{{ expanded === i ? '收起' : '展开' }}</button>
              </td>
            </tr>

            <!-- Expanded detail row -->
            <tr v-if="expanded === i" class="detail-row">
              <td :colspan="10">
                <div class="detail-panel">
                  <div v-if="row.missing_cols && Object.keys(row.missing_cols).length" class="detail-section">
                    <strong>缺失值 (按列)</strong>
                    <div class="tag-list">
                      <span v-for="(pct, col) in row.missing_cols" :key="col" class="health-tag tag-warn">
                        {{ col }}: {{ pct }}%
                      </span>
                    </div>
                  </div>
                  <div v-if="row.outlier_cols && Object.keys(row.outlier_cols).length" class="detail-section">
                    <strong>异常值 (按列, IQR×3)</strong>
                    <div class="tag-list">
                      <span v-for="(cnt, col) in row.outlier_cols" :key="col" class="health-tag tag-outlier">
                        {{ col }}: {{ cnt }}
                      </span>
                    </div>
                  </div>
                  <div v-if="row.error" class="detail-section">
                    <strong>错误</strong>
                    <p class="error-text">{{ row.error }}</p>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue";

interface HealthRow {
  table: string;
  files: number;
  rows: number;
  columns: number;
  size_mb: number;
  missing_pct: number;
  missing_cols: Record<string, number>;
  outlier_count: number;
  outlier_cols: Record<string, number>;
  freshness_days: number | null;
  error: string | null;
  checked_at: string;
}

interface HealthSummary {
  tables: number;
  total_size_mb: number;
  avg_missing_pct: number;
  total_outliers: number;
  checked_at: string;
}

const rows = ref<HealthRow[]>([]);
const summary = ref<HealthSummary | null>(null);
const status = ref<"loading" | "ok" | "no_data" | "error">("loading");
const expanded = ref<number | null>(null);

const statusClass = computed(() => `dot-${status.value}`);
const statusText = computed(() => {
  if (status.value === "loading") return "加载中...";
  if (status.value === "no_data") return "尚未运行健康检查，请等待周六自动扫描";
  if (status.value === "error") return "加载失败";
  return "健康检查完成";
});

const missingColor = computed(() => {
  const v = summary.value?.avg_missing_pct ?? 0;
  if (v < 3) return "var(--positive)";
  if (v < 10) return "var(--warning)";
  return "var(--negative)";
});

const outlierColor = computed(() => {
  const v = summary.value?.total_outliers ?? 0;
  if (v < 1000) return "var(--positive)";
  if (v < 10000) return "var(--warning)";
  return "var(--negative)";
});

function fmtSize(mb: number | undefined | null): string {
  if (mb == null) return "—";
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${(mb * 1024).toFixed(0)} KB`;
}

function fmtPercent(v: number | undefined | null): string {
  if (v == null) return "—";
  return `${v.toFixed(1)}%`;
}

function fmtCount(v: number | undefined | null): string {
  if (v == null) return "—";
  if (v >= 1000000) return `${(v / 1000000).toFixed(1)}M`;
  if (v >= 1000) return `${(v / 1000).toFixed(1)}K`;
  return String(v);
}

function fmtTime(iso: string | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return iso.slice(0, 16);
  }
}

function freshnessLabel(days: number | null): string {
  if (days == null) return "—";
  if (days === 0) return "今天";
  if (days === 1) return "1天前";
  if (days <= 7) return `${days}天前`;
  if (days <= 30) return `${days}天前`;
  if (days <= 365) return `${Math.round(days / 30)}月前`;
  return `${Math.round(days / 365)}年前`;
}

function missingClass(pct: number | null | undefined): string {
  if (pct == null) return "";
  if (pct === 0) return "val-ok";
  if (pct < 5) return "val-warn";
  return "val-bad";
}

function outlierClass(cnt: number | null | undefined): string {
  if (cnt == null) return "";
  if (cnt === 0) return "val-ok";
  if (cnt < 100) return "val-warn";
  return "val-bad";
}

function freshnessClass(days: number | null): string {
  if (days == null) return "";
  if (days <= 1) return "val-ok";
  if (days <= 7) return "val-warn";
  return "val-bad";
}

function hasDetail(row: HealthRow): boolean {
  return !!(
    (row.missing_cols && Object.keys(row.missing_cols).length) ||
    (row.outlier_cols && Object.keys(row.outlier_cols).length) ||
    row.error
  );
}

function toggleDetail(i: number) {
  expanded.value = expanded.value === i ? null : i;
}

async function fetchData() {
  status.value = "loading";
  try {
    const resp = await fetch("/api/system/db-health");
    const data = await resp.json();
    if (data.status === "no_data") {
      status.value = "no_data";
      rows.value = [];
      summary.value = null;
      return;
    }
    rows.value = data.data || [];
    summary.value = data.summary || null;
    status.value = "ok";
  } catch {
    status.value = "error";
  }
}

onMounted(fetchData);
</script>

<style scoped>
.db-health { padding: 20px 24px; max-width: 1200px; }

/* Hero */
.health-hero {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

/* Status bar */
.status-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.status-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-loading { background: var(--warning); animation: pulse 1.5s infinite; }
.dot-ok { background: var(--positive); }
.dot-no_data { background: var(--text-secondary); }
.dot-error { background: var(--negative); }

@keyframes pulse { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }

.checked-at { margin-left: auto; opacity: 0.6; }

/* Table */
.table-wrap {
  overflow-x: auto;
  background: rgba(255,255,255,0.02);
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.05);
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

thead th {
  text-align: left;
  padding: 10px 12px;
  color: var(--text-secondary);
  font-weight: 500;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  position: sticky;
  top: 0;
  background: rgba(2,6,23,0.95);
  backdrop-filter: blur(8px);
}
th.num { text-align: right; }

tbody td {
  padding: 9px 12px;
  border-bottom: 1px solid rgba(255,255,255,0.03);
  white-space: nowrap;
}
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.mono { font-family: var(--font-mono, "JetBrains Mono", monospace); }

.table-name {
  display: flex;
  align-items: center;
  gap: 6px;
}
.name-text {
  font-family: var(--font-mono, "JetBrains Mono", monospace);
  font-size: 12px;
  color: var(--text-primary);
}
.error-badge {
  color: var(--negative);
  font-size: 12px;
  cursor: help;
}

.row-error { background: rgba(239,68,68,0.03); }
.row-error .name-text { color: var(--negative); }

.source-cell {
  font-size: 11px;
  color: var(--text-secondary);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Value colors */
.val-ok { color: var(--positive); }
.val-warn { color: var(--warning); }
.val-bad { color: var(--negative); }

/* Detail */
.detail-btn {
  background: none;
  border: 1px solid rgba(255,255,255,0.1);
  color: var(--text-secondary);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
}
.detail-btn:hover { border-color: var(--accent); color: var(--accent); }

.detail-row td { padding: 0; border: none; }
.detail-panel {
  padding: 12px 16px;
  background: rgba(255,255,255,0.01);
  border-bottom: 1px solid rgba(255,255,255,0.04);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-section strong {
  display: block;
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.health-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: var(--font-mono, "JetBrains Mono", monospace);
}
.tag-warn { background: rgba(245,158,11,0.1); color: var(--warning); }
.tag-outlier { background: rgba(239,68,68,0.08); color: var(--negative); }

.error-text {
  margin: 0;
  font-size: 12px;
  color: var(--negative);
  font-family: var(--font-mono, "JetBrains Mono", monospace);
}

.telemetry-card {
  padding: 16px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.05);
  background: rgba(255,255,255,0.02);
}
.metric-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
}
.metric-head small { font-size: 11px; opacity: 0.6; }
.metric-main {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.metric-main strong {
  font-size: 28px;
  font-weight: 600;
  font-family: var(--font-mono, "JetBrains Mono", monospace);
}
.metric-main span {
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
