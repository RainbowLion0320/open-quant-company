<template>
  <div class="system-page view-page">
    <section class="system-hero">
      <article class="telemetry-card glass-card">
        <div class="metric-head">
          <span>CPU</span>
          <small>{{ monitor?.cpu?.cores_physical ?? '—' }} cores</small>
        </div>
        <div class="metric-main">
          <strong :style="{ color: cpuColor }">{{ fmtPercent(monitor?.cpu?.percent) }}</strong>
          <span>{{ loadText }}</span>
        </div>
        <div class="meter-track"><i :style="{ width: pctWidth(monitor?.cpu?.percent), background: cpuColor }"></i></div>
        <div class="metric-foot">
          <span>Load Average</span>
          <em>{{ loadText }}</em>
        </div>
      </article>

      <article class="telemetry-card glass-card">
        <div class="metric-head">
          <span>MEMORY</span>
          <small>{{ fmtGb(monitor?.memory?.used_gb) }} / {{ fmtGb(monitor?.memory?.total_gb) }}</small>
        </div>
        <div class="metric-main">
          <strong :style="{ color: memColor }">{{ fmtPercent(monitor?.memory?.percent) }}</strong>
          <span>{{ fmtGb(monitor?.memory?.used_gb) }} used</span>
        </div>
        <div class="meter-track"><i :style="{ width: pctWidth(monitor?.memory?.percent), background: memColor }"></i></div>
        <div class="metric-foot">
          <span>Battery</span>
          <em>{{ batteryText }}</em>
        </div>
      </article>

      <article class="telemetry-card glass-card">
        <div class="metric-head">
          <span>DISK</span>
          <small>{{ fmtGb(monitor?.disk?.used_gb) }} / {{ fmtGb(monitor?.disk?.total_gb) }}</small>
        </div>
        <div class="metric-main">
          <strong style="color:var(--text-secondary)">{{ fmtPercent(monitor?.disk?.percent) }}</strong>
          <span>{{ fmtGb(monitor?.disk?.used_gb) }} used</span>
        </div>
        <div class="meter-track"><i :style="{ width: pctWidth(monitor?.disk?.percent), background: 'var(--text-secondary)' }"></i></div>
        <div class="metric-foot">
          <span>Updated {{ elapsed }}s ago</span>
          <button @click="fetchData" class="icon-button" aria-label="刷新">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/></svg>
          </button>
        </div>
      </article>
    </section>

    <section class="system-grid">
      <div class="deepseek-panel glass-card">
        <div class="panel-head">
          <span>DEEPSEEK USAGE · 30D</span>
          <div class="usage-total">
            <span class="tag-badge cyan">PRO {{ fmtNum(dsTotals?.pro ?? 0) }}</span>
            <span class="tag-badge violet">FLASH {{ fmtNum(dsTotals?.flash ?? 0) }}</span>
            <span class="tag-badge amber">¥{{ (dsTotals?.cost ?? 0).toFixed(0) }}</span>
          </div>
        </div>

        <div class="usage-summary">
          <div>
            <span>v4-pro tokens</span>
            <strong>{{ fmtNum(dsTotals?.pro ?? 0) }}</strong>
          </div>
          <div>
            <span>v4-flash tokens</span>
            <strong>{{ fmtNum(dsTotals?.flash ?? 0) }}</strong>
          </div>
          <div>
            <span>estimated CNY</span>
            <strong>¥{{ (dsTotals?.cost ?? 0).toFixed(0) }}</strong>
          </div>
        </div>

        <div class="chart-stack">
          <div class="chart-block">
            <div class="ds-chart-label">v4-pro token stack</div>
            <canvas ref="dsProRef"></canvas>
          </div>
          <div class="chart-block">
            <div class="ds-chart-label">v4-flash token stack</div>
            <canvas ref="dsFlashRef"></canvas>
          </div>
          <div class="chart-block cost">
            <div class="ds-chart-label">daily cost</div>
            <canvas ref="dsCostRef"></canvas>
          </div>
        </div>
        <div class="chart-legend">
          <span><span class="legend-swatch" style="background:rgba(6,95,107,0.85)"></span>计费输入</span>
          <span><span class="legend-swatch" style="background:rgba(6,182,212,0.85)"></span>输出</span>
          <span><span class="legend-swatch" style="background:rgba(6,182,212,0.25);border:1px dashed rgba(6,182,212,0.3)"></span>缓存命中</span>
          <span><span class="legend-swatch" style="background:rgba(61,21,120,0.85)"></span>v4-flash</span>
        </div>
      </div>

      <aside class="system-side">
        <div class="glass-card side-card">
          <div class="panel-head">
            <span>RESOURCE HISTORY</span>
            <small>{{ historyHours }}h</small>
          </div>
          <div class="resource-charts">
            <div>
              <canvas :id="cpuChartId"></canvas>
              <div>CPU %</div>
            </div>
            <div>
              <canvas :id="memChartId"></canvas>
              <div>MEM %</div>
            </div>
          </div>
        </div>

        <div class="glass-card side-card">
          <div class="panel-head">
            <span>TOP PROCESSES</span>
            <small>{{ monitor?.top_processes?.length ?? 0 }} rows</small>
          </div>
          <div class="table-shell compact-table" style="--table-min:0">
            <table class="data-table">
              <colgroup>
                <col style="width:62%"><col style="width:19%"><col style="width:19%">
              </colgroup>
              <thead>
                <tr><th>Process</th><th class="text-right">CPU</th><th class="text-right">MEM</th></tr>
              </thead>
              <tbody>
                <tr v-for="p in monitor?.top_processes ?? []" :key="p.pid">
                  <td class="font-mono process-name">{{ p.name }}</td>
                  <td class="text-right font-mono">{{ p.cpu }}%</td>
                  <td class="text-right font-mono">{{ p.mem }}%</td>
                </tr>
              </tbody>
            </table>
            <div v-if="!(monitor?.top_processes?.length)" class="mini-empty">暂无进程采样</div>
          </div>
        </div>
      </aside>
    </section>

    <section class="system-settings">
      <div class="glass-card settings-card">
        <div class="panel-head">
          <span>TELEGRAM</span>
        </div>
        <div class="settings-row main">
          <div>
            <strong>信号推送</strong>
            <span>每日 15:30 → @buffett0320_bot</span>
          </div>
          <button @click="toggleNotify"
            class="toggle-switch"
            :class="{ active: sysSettings.trading?.notification?.enabled }">
            <span></span>
          </button>
        </div>
      </div>
      <div class="glass-card settings-card">
        <div class="panel-head">
          <span>DATA SOURCES</span>
        </div>
        <div class="source-list">
          <div><span>AKShare</span><em class="badge-ok">正常</em></div>
          <div><span>Tushare MCP</span><em class="badge-ok">正常</em></div>
          <div><span>Hindsight (pg0)</span><em class="badge-ok">正常</em></div>
          <div><span>Parquet / DuckDB</span><em class="badge-ok">正常</em></div>
        </div>
      </div>
      <div class="glass-card settings-card">
        <div class="panel-head">
          <span>SYSTEM INFO</span>
        </div>
        <div class="info-grid">
          <div><span>Version</span><strong>v5.1 Quantum Terminal</strong></div>
          <div><span>API Port</span><strong>8501</strong></div>
          <div><span>Pool</span><strong>5204 stocks</strong></div>
          <div><span>Strategies</span><strong>4 active</strong></div>
          <div><span>Factors</span><strong>35+</strong></div>
          <div><span>Cron</span><strong>15:30 CST</strong></div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onUnmounted } from "vue";
import { api, type SystemMonitor } from "../api";

const monitor = ref<SystemMonitor | null>(null);
const lastFetch = ref(Date.now());
const elapsed = ref(0);
const historyHours = ref(24);
let timer: number | undefined;
let elapTimer: number | undefined;

const cpuColor = computed(() => {
  const p = monitor.value?.cpu?.percent ?? 0;
  if (p > 80) return "var(--negative)"; if (p > 50) return "var(--warning)"; return "var(--positive)";
});
const memColor = computed(() => {
  const p = monitor.value?.memory?.percent ?? 0;
  if (p > 85) return "var(--negative)"; if (p > 60) return "var(--warning)"; return "var(--positive)";
});
const loadText = computed(() => (monitor.value?.cpu?.load_avg ?? []).map(v => Number(v).toFixed(2)).join(" / ") || "—");
const batteryText = computed(() => {
  const bat = monitor.value?.battery;
  if (!bat) return "—";
  return `${bat.percent ?? "—"}%${bat.charging ? " · charging" : ""}`;
});

const cpuChartId = "cpu-chart"; const memChartId = "mem-chart";
const dsProRef = ref<HTMLCanvasElement | null>(null);
const dsFlashRef = ref<HTMLCanvasElement | null>(null);
const dsCostRef = ref<HTMLCanvasElement | null>(null);
const dsTotals = ref<{ pro: number; flash: number; cost: number } | null>(null);

const sysSettings = reactive<Record<string, any>>({});

async function toggleNotify() {
  const enabled = !sysSettings.trading?.notification?.enabled;
  sysSettings.trading = sysSettings.trading || {};
  sysSettings.trading.notification = sysSettings.trading.notification || {};
  sysSettings.trading.notification.enabled = enabled;
  try { await api.saveSettings(sysSettings); } catch {}
}

async function loadSettings() {
  try { const d = await api.settings(); Object.assign(sysSettings, d); } catch {}
}

function fmtNum(n: number): string {
  if (n > 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n > 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(Math.round(n));
}
function fmtGb(v: number | undefined | null): string {
  if (v == null || Number.isNaN(Number(v))) return "— GB";
  return `${Number(v).toFixed(1)} GB`;
}
function fmtPercent(v: number | undefined | null): string {
  if (v == null || Number.isNaN(Number(v))) return "—%";
  return `${Number(v).toFixed(1)}%`;
}
function pctWidth(v: number | undefined | null): string {
  return `${Math.max(0, Math.min(100, Number(v || 0)))}%`;
}

async function fetchData() {
  try {
    const next = await api.systemMonitor();
    monitor.value = (next as any).status === "no_data" ? null : next;
    lastFetch.value = Date.now();
    drawCharts();
    drawDSChart();
  } catch (e) { /* silent */ }
}

function drawCharts() {
  const charts = [
    { id: cpuChartId, key: "cpu_pct" as const, color: "#06b6d4", max: 100 },
    { id: memChartId, key: "mem_pct" as const, color: "#10b981", max: 100 },
  ];
  fetch(`/api/system/history?hours=${historyHours.value}`).then(r => r.json()).then(hist => {
    const pts = hist.data || [];
    for (const ch of charts) {
      const canvas = document.getElementById(ch.id) as HTMLCanvasElement;
      if (!canvas) continue;
      const ctx = canvas.getContext("2d");
      if (!ctx) continue;
      const width = canvas.offsetWidth || 240;
      const height = canvas.offsetHeight || 112;
      canvas.width = width * 2;
      canvas.height = height * 2;
      ctx.scale(2, 2);
      const W = width, H = height;
      ctx.clearRect(0, 0, W, H);
      if (pts.length < 2) continue;
      const vals = pts.map((p: any) => p[ch.key] || 0);
      const maxVal = ch.max || Math.max(...vals, 1);
      ctx.beginPath();
      ctx.strokeStyle = ch.color;
      ctx.lineWidth = 1.5;
      for (let i = 0; i < vals.length; i++) {
        const x = (i / (vals.length - 1)) * (W - 10) + 5;
        const y = H - (vals[i] / maxVal) * (H - 10) - 5;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
  }).catch(() => {});
}

async function drawDSChart() {
  try {
    const res = await fetch("/api/system/deepseek-usage");
    const d = await res.json();
    if (!d.data || d.data.length === 0) return;
    const rows: any[] = d.data;
    if (rows.length < 2) return;
    const dates: string[] = [];
    const today = new Date();
    for (let i = 29; i >= 0; i--) {
      const dt = new Date(today); dt.setDate(dt.getDate() - i);
      dates.push(dt.toISOString().slice(0, 10));
    }
    const rowByDate: Record<string, any> = {};
    for (const r of rows) rowByDate[r.utc_date + "|" + r.model] = r;
    const proRows = rows.filter((r: any) => r.model === "deepseek-v4-pro");
    const flashRows = rows.filter((r: any) => r.model === "deepseek-v4-flash");
    dsTotals.value = {
      pro: proRows.reduce((s: number, r: any) => s + (r.input_cache_miss||0)+(r.output_tokens||0)+(r.input_cache_hit||0), 0),
      flash: flashRows.reduce((s: number, r: any) => s + (r.input_cache_miss||0)+(r.output_tokens||0)+(r.input_cache_hit||0), 0),
      cost: rows.reduce((s: number, r: any) => s + (r.cost_cny||0), 0),
    };

    const models = [
      { key: "deepseek-v4-pro",   ref: dsProRef,   colors: ["rgba(6,95,107,0.85)","rgba(6,182,212,0.85)","rgba(6,182,212,0.28)"] },
      { key: "deepseek-v4-flash", ref: dsFlashRef, colors: ["rgba(61,21,120,0.85)","rgba(124,58,237,0.85)","rgba(124,58,237,0.28)"] },
    ];
    const layers = ["input_cache_miss", "output_tokens", "input_cache_hit"];

    for (const model of models) {
      const canvas = model.ref.value;
      if (!canvas) continue;
      const ctx = canvas.getContext("2d");
      if (!ctx) continue;
      const dpr = 2;
      const W = canvas.offsetWidth || 320, H = canvas.offsetHeight || 112;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.scale(dpr, dpr); ctx.clearRect(0, 0, W, H);

      const modelRows = rows.filter((r: any) => r.model === model.key);
      const maxVal = Math.max(...modelRows.map((r: any) => (r.input_cache_miss||0)+(r.output_tokens||0)+(r.input_cache_hit||0)), 1);
      const leftPad = 34, botPad = 16;
      const chartH = H - 6 - botPad;
      const slotW = (W - leftPad - 2) / dates.length;
      const barW = Math.max(1, slotW * 0.20);

      ctx.fillStyle = "#64748b"; ctx.font = "8px monospace";
      for (let t = 0; t <= maxVal; t += maxVal / 3) {
        const y = H - botPad - (t / maxVal) * chartH;
        ctx.fillText(t>=1e6?(t/1e6).toFixed(0)+"M":t>=1e3?(t/1e3).toFixed(0)+"K":String(t), 2, y+3);
        ctx.strokeStyle = "rgba(148,163,184,0.05)"; ctx.lineWidth = 0.5;
        ctx.beginPath(); ctx.moveTo(leftPad, y); ctx.lineTo(W-2, y); ctx.stroke();
      }
      dates.forEach((date, di) => {
        const row = rowByDate[date + "|" + model.key];
        if (!row) return;
        const x0 = leftPad + di * slotW + (slotW - barW) / 2;
        let yBottom = H - botPad;
        layers.forEach((layer, li) => {
          const val = row[layer] || 0;
          const h = (val / maxVal) * chartH;
          ctx.fillStyle = model.colors[li];
          ctx.fillRect(x0, yBottom - h, barW, h);
          yBottom -= h;
        });
        if (di % 3 === 0) { ctx.fillStyle = "#64748b"; ctx.font = "7px monospace"; ctx.fillText(date.slice(5), x0, H-3); }
      });
    }

    // Cost chart
    const costCanvas = dsCostRef.value;
    if (costCanvas) {
      const ctx = costCanvas.getContext("2d");
      if (ctx) {
        const dpr = 2;
        const W = costCanvas.offsetWidth || 320, H = costCanvas.offsetHeight || 82;
        costCanvas.width = W * dpr; costCanvas.height = H * dpr;
        ctx.scale(dpr, dpr); ctx.clearRect(0, 0, W, H);
        const costs = rows.filter((r: any) => r.cost_cny > 0);
        const maxCost = Math.max(...costs.map((r: any) => r.cost_cny), 1);
        const leftPad = 34, botPad = 14, chartH = H - 8 - botPad;
        const slotWc = (W - leftPad - 2) / dates.length;
        const barWc = Math.max(1, slotWc * 0.20);
        ctx.fillStyle = "#64748b"; ctx.font = "8px monospace";
        for (let t = 0; t <= maxCost; t += maxCost / 3) {
          const y = H - botPad - (t / maxCost) * chartH;
          ctx.fillText("¥"+t.toFixed(0), 2, y+3);
          ctx.strokeStyle = "rgba(148,163,184,0.05)"; ctx.lineWidth = 0.5;
          ctx.beginPath(); ctx.moveTo(leftPad, y); ctx.lineTo(W-2, y); ctx.stroke();
        }
        const costByDate: Record<string, number> = {};
        for (const r of costs) costByDate[r.utc_date] = (costByDate[r.utc_date]||0) + r.cost_cny;
        const costDates = dates.filter(d => costByDate[d] > 0);
        if (costDates.length > 0) {
          for (const date of costDates) {
            const di = dates.indexOf(date), val = costByDate[date];
            const x0 = leftPad + di * slotWc + (slotWc - barWc) / 2;
            ctx.fillStyle = "rgba(6,182,212,0.35)";
            ctx.fillRect(x0, H - botPad - (val/maxCost)*chartH, barWc, (val/maxCost)*chartH);
          }
          ctx.beginPath(); ctx.strokeStyle = "#06b6d4"; ctx.lineWidth = 1.2;
          for (let i = 0; i < costDates.length; i++) {
            const di = dates.indexOf(costDates[i]), val = costByDate[costDates[i]];
            const x = leftPad + di * slotWc + slotWc / 2;
            const y = H - botPad - (val/maxCost)*chartH;
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }
        dates.forEach((date, di) => {
          if (di % 3 === 0) { ctx.fillStyle = "#64748b"; ctx.font = "7px monospace"; ctx.fillText(date.slice(5), leftPad + di*slotWc, H-2); }
        });
      }
    }
  } catch (e) { /* silent */ }
}

onMounted(() => {
  fetchData();
  loadSettings();
  timer = window.setInterval(fetchData, 10_000);
  elapTimer = window.setInterval(() => { elapsed.value = Math.round((Date.now() - lastFetch.value) / 1000); }, 1000);
});
onUnmounted(() => { if (timer) clearInterval(timer); if (elapTimer) clearInterval(elapTimer); });
</script>

<style scoped>
.system-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.system-hero {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.system-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(330px, 0.8fr);
  gap: 12px;
  align-items: start;
}
.system-settings {
  display: grid;
  grid-template-columns: minmax(260px, 0.8fr) minmax(280px, 1fr) minmax(320px, 1.15fr);
  gap: 12px;
}
.telemetry-card,
.deepseek-panel,
.side-card,
.settings-card {
  padding: 14px;
}
.telemetry-card {
  min-height: 132px;
}
.metric-head,
.metric-foot,
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.metric-head {
  margin-bottom: 14px;
}
.metric-head span,
.panel-head span {
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.metric-head small,
.panel-head small {
  color: var(--text-disabled);
  font-size: 10px;
  white-space: nowrap;
}
.metric-main {
  display: flex;
  align-items: baseline;
  gap: 12px;
}
.metric-main strong {
  font-family: "JetBrains Mono", monospace;
  font-size: clamp(26px, 3vw, 38px);
  line-height: 1;
  letter-spacing: 0;
}
.metric-main span {
  color: var(--text-tertiary);
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
}
.meter-track {
  height: 4px;
  margin-top: 12px;
  border-radius: 999px;
  background: rgba(125, 211, 252, 0.08);
  overflow: hidden;
}
.meter-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  box-shadow: 0 0 14px currentColor;
  transition: width 0.4s ease;
}
.metric-foot {
  margin-top: 12px;
  color: var(--text-disabled);
  font-size: 11px;
}
.metric-foot em {
  color: var(--text-secondary);
  font-style: normal;
  font-family: "JetBrains Mono", monospace;
}
.metric-foot .icon-button {
  margin-left: auto;
}

/* ── Shared with Market.vue style ── */
.panel-head {
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 12px;
}

/* ── Charts ── */
.usage-total {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}
.usage-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 12px;
}
.usage-summary div {
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.14);
}
.usage-summary span {
  display: block;
  color: var(--text-disabled);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.usage-summary strong {
  display: block;
  margin-top: 4px;
  color: var(--text-primary);
  font-family: "JetBrains Mono", monospace;
  font-size: 15px;
}
.chart-stack {
  display: grid;
  gap: 10px;
}
.chart-block {
  min-height: 142px;
  padding: 8px 10px 6px;
  border: 1px solid rgba(125, 211, 252, 0.06);
  border-radius: 7px;
  background: rgba(3, 10, 18, 0.18);
}
.chart-block.cost {
  min-height: 108px;
}
.chart-block canvas {
  display: block;
  width: 100%;
  height: 112px;
}
.chart-block.cost canvas {
  height: 82px;
}
.ds-chart-label {
  font-size: 9px;
  color: var(--text-disabled);
  letter-spacing: 0.09em;
  margin-bottom: 5px;
  text-transform: uppercase;
}
.chart-legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px 12px;
  margin-top: 10px;
  font-size: 10px;
  color: var(--text-disabled);
}
.legend-swatch {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  margin-right: 3px;
  vertical-align: middle;
}
.legend-sep { color: #475569; margin: 0 2px; }
.system-side {
  display: grid;
  gap: 12px;
}
.resource-charts {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}
.resource-charts canvas {
  display: block;
  width: 100%;
  height: 112px;
}
.resource-charts div div {
  margin-top: 4px;
  color: var(--text-disabled);
  font-size: 10px;
  text-align: center;
  letter-spacing: 0.08em;
}
.compact-table .data-table td,
.compact-table .data-table th {
  height: 34px;
  padding-top: 7px;
  padding-bottom: 7px;
}
.process-name {
  color: var(--text-secondary);
}
.mini-empty {
  padding: 18px 10px;
  color: var(--text-disabled);
  font-size: 11px;
  text-align: center;
}

/* ── Toggle ── */
.toggle-switch {
  position: relative;
  width: 40px;
  height: 22px;
  border-radius: 999px;
  background: var(--border-strong);
  border: none;
  cursor: pointer;
  transition: background 0.2s;
}
.toggle-switch.active { background: var(--accent); }
.toggle-switch span {
  position: absolute;
  top: 2px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: left 0.2s;
}
.toggle-switch:not(.active) span { left: 2px; }
.toggle-switch.active span { left: 20px; }

/* ── Badge / Icon ── */
.badge-ok {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(16,185,129,0.15);
  color: #10b981;
  font-style: normal;
  white-space: nowrap;
}
.tag-badge {
  font-size: 9px;
  font-family: "JetBrains Mono", monospace;
  padding: 2px 7px;
  border-radius: 4px;
  white-space: nowrap;
  border: 1px solid transparent;
}
.tag-badge.cyan { background:rgba(6,182,212,0.12); color:rgba(6,182,212,0.95); border-color:rgba(6,182,212,0.12); }
.tag-badge.violet { background:rgba(124,58,237,0.13); color:rgba(167,139,250,0.95); border-color:rgba(124,58,237,0.14); }
.tag-badge.amber { background:rgba(245,158,11,0.13); color:#f59e0b; border-color:rgba(245,158,11,0.14); }
.icon-button {
  width: 26px;
  height: 26px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(0, 212, 255, 0.04);
  color: var(--accent);
  cursor: pointer;
}
.icon-button svg {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.settings-row.main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.settings-row strong,
.source-list span,
.info-grid span {
  display: block;
}
.settings-row strong {
  color: var(--text-primary);
  font-size: 13px;
}
.settings-row span {
  margin-top: 2px;
  color: var(--text-disabled);
  font-size: 10px;
}
.source-list {
  display: grid;
  gap: 8px;
}
.source-list div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-primary);
  font-size: 12px;
}
.source-list div:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 14px;
}
.info-grid div {
  min-width: 0;
}
.info-grid span {
  color: var(--text-disabled);
  font-size: 9px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.info-grid strong {
  display: block;
  margin-top: 3px;
  color: var(--text-secondary);
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Responsive ── */
@media (max-width: 1180px) {
  .system-grid { grid-template-columns: 1fr; }
  .system-side { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 900px) {
  .system-hero { grid-template-columns: 1fr; }
  .system-side { grid-template-columns: 1fr; }
  .system-settings { grid-template-columns: 1fr; }
  .usage-summary { grid-template-columns: 1fr; }
  .panel-head {
    align-items: flex-start;
    flex-direction: column;
  }
  .usage-total {
    justify-content: flex-start;
  }
}
</style>
