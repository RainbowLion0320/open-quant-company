<template>
  <div class="system-page">
    <!-- ── Hero: CPU + Memory + Disk ── -->
    <section class="system-hero">
      <div class="glass-card">
        <div class="panel-head">
          <span>CPU</span>
          <small>{{ data?.cpu.cores_physical }} Cores</small>
        </div>
        <div class="hero-value" :style="{ color: cpuColor }">{{ data?.cpu.percent ?? 0 }}%</div>
        <div class="progress-bar mt-2" :style="{ width: (data?.cpu.percent ?? 0) + '%', background: cpuColor }"></div>
        <div class="hero-foot">
          <span>Load</span>
          <div class="load-values">{{ (data?.cpu.load_avg ?? []).join(' / ') }}</div>
        </div>
      </div>
      <div class="glass-card">
        <div class="panel-head">
          <span>MEMORY</span>
          <small>{{ data?.memory.used_gb }} / {{ data?.memory.total_gb }} GB</small>
        </div>
        <div class="hero-value" :style="{ color: memColor }">{{ data?.memory.percent ?? 0 }}%</div>
        <div class="progress-bar mt-2" :style="{ width: (data?.memory.percent ?? 0) + '%', background: memColor }"></div>
        <div class="hero-foot">
          <span>Battery</span>
          <strong :style="{ color: 'var(--positive)' }">{{ data?.battery?.percent ?? '—' }}%</strong>
          <em v-if="data?.battery?.charging">⚡</em>
        </div>
      </div>
      <div class="glass-card">
        <div class="panel-head">
          <span>DISK</span>
          <small>{{ data?.disk.used_gb }} / {{ data?.disk.total_gb }} GB</small>
        </div>
        <div class="hero-value" style="color:var(--text-secondary)">{{ data?.disk.percent ?? 0 }}%</div>
        <div class="progress-bar mt-2" :style="{ width: (data?.disk.percent ?? 0) + '%', background: 'var(--text-secondary)' }"></div>
        <div class="hero-foot">
          <span>Updated</span>
          <em>{{ elapsed }}s ago</em>
          <button @click="fetchData" class="icon-button ml-auto" aria-label="刷新">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/></svg>
          </button>
        </div>
      </div>
    </section>

    <!-- ── DeepSeek Token Usage ── -->
    <section>
      <div class="glass-card">
        <div class="panel-head">
          <span>DEEPSEEK TOKEN USAGE · 过去30天</span>
          <div class="flex items-center gap-2">
            <span class="tag-badge" style="background:rgba(6,182,212,0.12);color:rgba(6,182,212,0.9)">v4-pro {{ fmtNum(dsTotals?.pro ?? 0) }}</span>
            <span class="tag-badge" style="background:rgba(124,58,237,0.12);color:rgba(124,58,237,0.9)">v4-flash {{ fmtNum(dsTotals?.flash ?? 0) }}</span>
            <span class="tag-badge" style="background:rgba(245,158,11,0.12);color:#f59e0b">¥{{ (dsTotals?.cost ?? 0).toFixed(0) }}</span>
          </div>
        </div>
        <div class="ds-chart-label">v4-pro</div>
        <canvas ref="dsProRef" class="w-full mb-3" style="height:120px"></canvas>
        <div class="ds-chart-label">v4-flash</div>
        <canvas ref="dsFlashRef" class="w-full mb-3" style="height:120px"></canvas>
        <div class="ds-chart-label">费用 ¥</div>
        <canvas ref="dsCostRef" class="w-full" style="height:90px"></canvas>
        <div class="chart-legend">
          <span><span class="legend-swatch" style="background:rgba(6,95,107,0.85)"></span>计费输入</span>
          <span><span class="legend-swatch" style="background:rgba(6,182,212,0.85)"></span>输出</span>
          <span><span class="legend-swatch" style="background:rgba(6,182,212,0.25);border:1px dashed rgba(6,182,212,0.3)"></span>缓存命中</span>
          <span class="legend-sep">|</span>
          <span><span class="legend-swatch" style="background:rgba(6,95,107,0.85)"></span>v4-pro</span>
          <span><span class="legend-swatch" style="background:rgba(61,21,120,0.85)"></span>v4-flash</span>
        </div>
      </div>
    </section>

    <!-- ── Resource History + Top Processes ── -->
    <section class="system-mid">
      <div class="glass-card">
        <div class="panel-head">
          <span>RESOURCE HISTORY</span>
          <small>{{ historyHours }}h</small>
        </div>
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <canvas :id="cpuChartId" class="w-full h-32"></canvas>
            <div class="text-2xs text-center" style="color:var(--text-disabled)">CPU %</div>
          </div>
          <div>
            <canvas :id="memChartId" class="w-full h-32"></canvas>
            <div class="text-2xs text-center" style="color:var(--text-disabled)">MEM %</div>
          </div>
        </div>
      </div>
      <div class="glass-card">
        <div class="panel-head">
          <span>TOP PROCESSES</span>
        </div>
        <div class="table-shell" style="--table-min:0">
          <table class="data-table">
            <colgroup>
              <col style="width:68%"><col style="width:16%"><col style="width:16%">
            </colgroup>
            <thead>
              <tr><th>Process</th><th class="text-right">CPU</th><th class="text-right">MEM</th></tr>
            </thead>
            <tbody>
              <tr v-for="p in data?.top_processes ?? []" :key="p.pid">
                <td class="font-mono" style="color:var(--text-secondary)">{{ p.name }}</td>
                <td class="text-right font-mono" style="color:var(--text-secondary)">{{ p.cpu }}%</td>
                <td class="text-right font-mono" style="color:var(--text-secondary)">{{ p.mem }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- ── Settings ── -->
    <section class="system-settings">
      <div class="glass-card">
        <div class="panel-head">
          <span>TELEGRAM</span>
        </div>
        <div class="flex items-center justify-between">
          <div>
            <div class="text-sm" style="color:var(--text-primary)">信号推送</div>
            <div class="text-2xs mt-0.5" style="color:var(--text-disabled)">每日 15:30 → @buffett0320_bot</div>
          </div>
          <button @click="toggleNotify"
            class="toggle-switch"
            :class="{ active: sysSettings.trading?.notification?.enabled }">
            <span></span>
          </button>
        </div>
      </div>
      <div class="glass-card">
        <div class="panel-head">
          <span>DATA SOURCES</span>
        </div>
        <div class="space-y-2">
          <div class="flex justify-between text-xs py-1" style="border-bottom:1px solid var(--border-subtle)"><span style="color:var(--text-primary)">AKShare</span><span class="badge-ok">正常</span></div>
          <div class="flex justify-between text-xs py-1" style="border-bottom:1px solid var(--border-subtle)"><span style="color:var(--text-primary)">Tushare MCP</span><span class="badge-ok">正常</span></div>
          <div class="flex justify-between text-xs py-1" style="border-bottom:1px solid var(--border-subtle)"><span style="color:var(--text-primary)">Hindsight (pg0)</span><span class="badge-ok">正常</span></div>
          <div class="flex justify-between text-xs py-1"><span style="color:var(--text-primary)">Parquet</span><span class="badge-ok">正常</span></div>
        </div>
      </div>
      <div class="glass-card">
        <div class="panel-head">
          <span>SYSTEM INFO</span>
        </div>
        <div class="grid grid-cols-1 gap-2 text-xs">
          <div class="flex justify-between py-1" style="border-bottom:1px solid var(--border-subtle)"><span style="color:var(--text-disabled)">Version</span><span class="font-mono" style="color:var(--text-secondary)">v4.0 Quantum Terminal</span></div>
          <div class="flex justify-between py-1" style="border-bottom:1px solid var(--border-subtle)"><span style="color:var(--text-disabled)">API Port</span><span class="font-mono" style="color:var(--text-secondary)">8501</span></div>
          <div class="flex justify-between py-1" style="border-bottom:1px solid var(--border-subtle)"><span style="color:var(--text-disabled)">Pool</span><span class="font-mono" style="color:var(--text-secondary)">5204 stocks</span></div>
          <div class="flex justify-between py-1" style="border-bottom:1px solid var(--border-subtle)"><span style="color:var(--text-disabled)">Strategies</span><span class="font-mono" style="color:var(--text-secondary)">4 (Buffett / MF / Cyb / ML)</span></div>
          <div class="flex justify-between py-1" style="border-bottom:1px solid var(--border-subtle)"><span style="color:var(--text-disabled)">Factors</span><span class="font-mono" style="color:var(--text-secondary)">35+</span></div>
          <div class="flex justify-between py-1" style="border-bottom:1px solid var(--border-subtle)"><span style="color:var(--text-disabled)">ML Model</span><span class="font-mono" style="color:var(--text-secondary)">LightGBM</span></div>
          <div class="flex justify-between py-1"><span style="color:var(--text-disabled)">Cron</span><span class="font-mono" style="color:var(--text-secondary)">15:30 CST</span></div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, onUnmounted } from "vue";
import { api, type SystemMonitor } from "../api";

const data = ref<SystemMonitor | null>(null);
const lastFetch = ref(Date.now());
const elapsed = ref(0);
const historyHours = ref(24);
let timer: number | undefined;
let elapTimer: number | undefined;

const cpuColor = computed(() => {
  const p = data.value?.cpu.percent ?? 0;
  if (p > 80) return "var(--negative)"; if (p > 50) return "var(--warning)"; return "var(--positive)";
});
const memColor = computed(() => {
  const p = data.value?.memory.percent ?? 0;
  if (p > 85) return "var(--negative)"; if (p > 60) return "var(--warning)"; return "var(--positive)";
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

async function fetchData() {
  try {
    data.value = await api.systemMonitor();
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
      const w = canvas.width = canvas.offsetWidth * 2;
      const h = canvas.height = canvas.offsetHeight * 2;
      ctx.scale(2, 2);
      const W = canvas.offsetWidth, H = canvas.offsetHeight;
      ctx.clearRect(0, 0, W, H);
      if (pts.length < 2) return;
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
      const W = canvas.offsetWidth, H = canvas.offsetHeight;
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
        const W = costCanvas.offsetWidth, H = costCanvas.offsetHeight;
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

    const proRows = rows.filter((r: any) => r.model === "deepseek-v4-pro");
    const flashRows = rows.filter((r: any) => r.model === "deepseek-v4-flash");
    dsTotals.value = {
      pro: proRows.reduce((s: number, r: any) => s + (r.input_cache_miss||0)+(r.output_tokens||0)+(r.input_cache_hit||0), 0),
      flash: flashRows.reduce((s: number, r: any) => s + (r.input_cache_miss||0)+(r.output_tokens||0)+(r.input_cache_hit||0), 0),
      cost: rows.reduce((s: number, r: any) => s + (r.cost_cny||0), 0),
    };
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
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.system-hero {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.system-mid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 12px;
}
.system-settings {
  display: grid;
  grid-template-columns: 300px 1fr 1fr;
  gap: 12px;
}

/* ── Shared with Market.vue style ── */
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
  margin-bottom: 10px;
}
.panel-head span {
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.panel-head small {
  color: var(--text-disabled);
  font-size: 10px;
}

/* ── Hero cards ── */
.hero-value {
  font-size: 36px;
  font-family: "JetBrains Mono", monospace;
  font-weight: 700;
  line-height: 1;
}
.hero-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  font-size: 11px;
  color: var(--text-disabled);
}
.hero-foot strong { color: var(--text-secondary); }
.hero-foot em { font-style: normal; margin-left: 2px; }

.load-values { font-family: "JetBrains Mono", monospace; font-size: 11px; color: var(--text-secondary); }

/* ── Progress bar ── */
.progress-bar {
  height: 3px;
  border-radius: 2px;
  transition: width 0.5s ease;
  min-width: 0;
}

/* ── Charts ── */
.ds-chart-label {
  font-size: 10px;
  color: var(--text-disabled);
  letter-spacing: 0.05em;
  margin-bottom: 2px;
}
.chart-legend {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 6px;
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
}
.tag-badge {
  font-size: 9px;
  font-family: "JetBrains Mono", monospace;
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
}
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

/* ── Responsive ── */
@media (max-width: 900px) {
  .system-hero { grid-template-columns: 1fr; }
  .system-mid { grid-template-columns: 1fr; }
  .system-settings { grid-template-columns: 1fr; }
}
</style>
