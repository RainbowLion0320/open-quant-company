<template>
  <div class="monitor-page">
    <div class="glass-card p-6">
      <div class="flex items-center gap-2 mb-4">
        <h2 class="text-lg font-semibold" style="color:var(--text-primary)">活动监视器</h2>
        <span class="text-2xs px-2 py-0.5 rounded" style="background:var(--bg-active);color:var(--text-disabled)">{{ elapsed }}s前</span>
        <button @click="fetchData" class="text-xs px-2 py-1 rounded" style="background:var(--accent);color:#000">刷新</button>
      </div>

      <!-- CPU + Memory + Disk row -->
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        <div class="metric-card">
          <div class="text-2xs" style="color:var(--text-disabled)">CPU</div>
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-mono font-bold" :style="{color: cpuColor}">{{ data?.cpu.percent ?? 0 }}%</span>
          </div>
          <div class="text-2xs" style="color:var(--text-disabled)">{{ data?.cpu.cores_physical }}核</div>
          <div class="progress-bar mt-1" :style="{width: (data?.cpu.percent ?? 0)+'%', background: cpuColor}"></div>
        </div>
        <div class="metric-card">
          <div class="text-2xs" style="color:var(--text-disabled)">内存</div>
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-mono font-bold" :style="{color: memColor}">{{ data?.memory.percent ?? 0 }}%</span>
          </div>
          <div class="text-2xs" style="color:var(--text-disabled)">{{ data?.memory.used_gb }} / {{ data?.memory.total_gb }} GB</div>
          <div class="progress-bar mt-1" :style="{width: (data?.memory.percent ?? 0)+'%', background: memColor}"></div>
        </div>
        <div class="metric-card">
          <div class="text-2xs" style="color:var(--text-disabled)">磁盘</div>
          <div class="flex items-baseline gap-1">
            <span class="text-2xl font-mono font-bold" style="color:var(--text-secondary)">{{ data?.disk.percent ?? 0 }}%</span>
          </div>
          <div class="text-2xs" style="color:var(--text-disabled)">{{ data?.disk.used_gb }} / {{ data?.disk.total_gb }} GB</div>
          <div class="progress-bar mt-1" :style="{width: (data?.disk.percent ?? 0)+'%', background: 'var(--text-secondary)'}"></div>
        </div>
      </div>

      <!-- Battery + Load -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <div class="metric-card">
          <div class="text-2xs" style="color:var(--text-disabled)">电池</div>
          <div class="flex items-center gap-1">
            <span class="text-xl font-mono font-bold" style="color:var(--positive)">{{ data?.battery?.percent ?? '—' }}%</span>
            <span class="text-2xs" style="color:var(--text-disabled)">{{ data?.battery?.charging ? 'charging' : 'battery' }}</span>
          </div>
        </div>
        <div class="metric-card">
          <div class="text-2xs" style="color:var(--text-disabled)">系统负载</div>
          <div class="load-values text-sm font-mono" style="color:var(--text-secondary)">
            <span v-for="(l, i) in data?.cpu.load_avg ?? []" :key="i">{{ l }}</span>
          </div>
        </div>
      </div>

      <!-- DeepSeek Token Usage Bar Chart -->
      <div class="metric-card p-4 mb-4" style="border-left:2px solid #e8a840">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <span class="text-2xs" style="color:var(--text-disabled)">DeepSeek Token 消耗趋势</span>
            <span class="tag-badge" style="background:rgba(6,182,212,0.12);color:rgba(6,182,212,0.9)">v4-pro {{ fmtNum(dsTotals?.pro ?? 0) }}</span>
            <span class="tag-badge" style="background:rgba(124,58,237,0.12);color:rgba(124,58,237,0.9)">v4-flash {{ fmtNum(dsTotals?.flash ?? 0) }}</span>
            <span class="tag-badge" style="background:rgba(245,158,11,0.12);color:#f59e0b">¥{{ (dsTotals?.cost ?? 0).toFixed(0) }}</span>
          </div>
          <span class="text-2xs" style="color:var(--accent)">过去30天</span>
        </div>
        <div class="text-2xs mb-1" style="color:var(--text-disabled)">v4-pro</div>
        <canvas ref="dsProRef" class="w-full mb-3" style="height:130px"></canvas>
        <div class="text-2xs mb-1" style="color:var(--text-disabled)">v4-flash</div>
        <canvas ref="dsFlashRef" class="w-full mb-3" style="height:130px"></canvas>
        <div class="text-2xs mb-1" style="color:var(--text-disabled)">费用 ¥</div>
        <canvas ref="dsCostRef" class="w-full" style="height:100px"></canvas>
        <div class="flex justify-center gap-3 mt-1 text-2xs" style="color:var(--text-disabled)">
          <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm" style="background:rgba(6,95,107,0.85)"></span>计费输入</span>
          <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm" style="background:rgba(6,182,212,0.85)"></span>输出</span>
          <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm" style="background:rgba(6,182,212,0.25);border:1px dashed rgba(6,182,212,0.3)"></span>缓存命中</span>
          <span class="mx-1" style="color:#475569">|</span>
          <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm" style="background:rgba(6,95,107,0.85)"></span>v4-pro</span>
          <span class="flex items-center gap-1"><span class="inline-block w-2 h-2 rounded-sm" style="background:rgba(61,21,120,0.85)"></span>v4-flash</span>
        </div>
      </div>

      <!-- Top Processes -->
      <div>
        <div class="text-2xs mb-2" style="color:var(--text-disabled)">高占用进程</div>
        <div class="table-shell" style="--table-min:420px">
          <table class="data-table">
            <colgroup>
              <col style="width:64%">
              <col style="width:18%">
              <col style="width:18%">
            </colgroup>
            <thead>
              <tr><th>进程</th><th class="text-right">CPU</th><th class="text-right">内存</th></tr>
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
    </div>

    <!-- History Charts -->
    <div class="glass-card p-6 mt-4">
      <h3 class="text-sm font-semibold mb-3" style="color:var(--text-primary)">历史趋势 ({{ historyHours }}h)</h3>
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div>
          <canvas :id="cpuChartId" class="w-full h-32"></canvas>
          <div class="text-2xs text-center" style="color:var(--text-disabled)">CPU %</div>
        </div>
        <div>
          <canvas :id="memChartId" class="w-full h-32"></canvas>
          <div class="text-2xs text-center" style="color:var(--text-disabled)">内存 %</div>
        </div>
        <div>
          <canvas :id="tokenChartId" class="w-full h-32"></canvas>
          <div class="text-2xs text-center" style="color:var(--text-disabled)">Token $</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
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

const cpuChartId = "cpu-chart"; const memChartId = "mem-chart"; const tokenChartId = "token-chart";
const dsProRef = ref<HTMLCanvasElement | null>(null);
const dsFlashRef = ref<HTMLCanvasElement | null>(null);
const dsCostRef = ref<HTMLCanvasElement | null>(null);
const dsTotals = ref<{ pro: number; flash: number; cost: number } | null>(null);

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
  // Lightweight canvas chart — no ECharts dependency
  const charts = [
    { id: cpuChartId, key: "cpu_pct" as const, color: "#06b6d4", max: 100 },
    { id: memChartId, key: "mem_pct" as const, color: "#10b981", max: 100 },
    { id: tokenChartId, key: "token_total_cost" as const, color: "#f59e0b", max: 0 },
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
    // Generate last 30 calendar days (fill missing with 0)
    const dates: string[] = [];
    const today = new Date();
    for (let i = 29; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      dates.push(d.toISOString().slice(0, 10));
    }
    // Index rows by date+model for fast lookup
    const rowByDate: Record<string, any> = {};
    for (const r of rows) rowByDate[r.utc_date + "|" + r.model] = r;

    const models = [
      { key: "deepseek-v4-pro",   ref: dsProRef,   colors: ["rgba(6,95,107,0.85)","rgba(6,182,212,0.85)","rgba(6,182,212,0.28)"] },
      { key: "deepseek-v4-flash", ref: dsFlashRef, colors: ["rgba(61,21,120,0.85)","rgba(124,58,237,0.85)","rgba(124,58,237,0.28)"] },
    ];
    const layers = ["input_cache_miss", "output_tokens", "input_cache_hit"];

    // ── Token stacked bars ──
    for (const model of models) {
      const canvas = model.ref.value;
      if (!canvas) continue;
      const ctx = canvas.getContext("2d");
      if (!ctx) continue;
      const dpr = 2;
      const W = canvas.offsetWidth, H = canvas.offsetHeight;
      canvas.width = W * dpr; canvas.height = H * dpr;
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, W, H);

      const modelRows = rows.filter((r: any) => r.model === model.key);
      const maxVal = Math.max(...modelRows.map((r: any) =>
        (r.input_cache_miss||0) + (r.output_tokens||0) + (r.input_cache_hit||0)
      ), 1);

      const leftPad = 34, topPad = 6, botPad = 16;
      const chartH = H - topPad - botPad;
      const slotW = (W - leftPad - 2) / dates.length;
      const barW = Math.max(1, slotW * 0.20);

      ctx.fillStyle = "#64748b"; ctx.font = "8px monospace";
      for (let t = 0; t <= maxVal; t += maxVal / 3) {
        const y = H - botPad - (t / maxVal) * chartH;
        const label = t >= 1_000_000 ? (t/1_000_000).toFixed(0)+"M" : t>=1000 ? (t/1000).toFixed(0)+"K" : String(t);
        ctx.fillText(label, 2, y + 3);
        ctx.strokeStyle = "rgba(148,163,184,0.05)"; ctx.lineWidth = 0.5;
        ctx.beginPath(); ctx.moveTo(leftPad, y); ctx.lineTo(W - 2, y); ctx.stroke();
      }

      dates.forEach((date: string, di: number) => {
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
        if (dates.length <= 14 || di % 3 === 0) {
          ctx.fillStyle = "#64748b"; ctx.font = "7px monospace";
          ctx.fillText(date.slice(5), x0, H - 3);
        }
      });
    }

    // ── Cost line chart ──
    const costCanvas = dsCostRef.value;
    if (costCanvas) {
      const ctx = costCanvas.getContext("2d");
      if (ctx) {
        const dpr = 2;
        const W = costCanvas.offsetWidth, H = costCanvas.offsetHeight;
        costCanvas.width = W * dpr; costCanvas.height = H * dpr;
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, W, H);

        const costs = rows.filter((r: any) => r.cost_cny > 0);
        const maxCost = Math.max(...costs.map((r: any) => r.cost_cny), 1);
        const leftPad = 34, botPad = 14, chartH = H - 8 - botPad;
        const slotWc = (W - leftPad - 2) / dates.length;
        const barWc = Math.max(1, slotWc * 0.20);

        // Y grid
        ctx.fillStyle = "#64748b"; ctx.font = "8px monospace";
        for (let t = 0; t <= maxCost; t += maxCost / 3) {
          const y = H - botPad - (t / maxCost) * chartH;
          ctx.fillText("¥" + t.toFixed(0), 2, y + 3);
          ctx.strokeStyle = "rgba(148,163,184,0.05)"; ctx.lineWidth = 0.5;
          ctx.beginPath(); ctx.moveTo(leftPad, y); ctx.lineTo(W - 2, y); ctx.stroke();
        }

        // Group by utc_date, sum cost across models
        const costByDate: Record<string, number> = {};
        for (const r of costs) {
          costByDate[r.utc_date] = (costByDate[r.utc_date] || 0) + r.cost_cny;
        }

        // Bars + fill area
        const costDates = dates.filter(d => costByDate[d] > 0);
        if (costDates.length > 0) {
          // Draw bars
          for (const date of costDates) {
            const di = dates.indexOf(date);
            const val = costByDate[date];
            const x0 = leftPad + di * slotWc + (slotWc - barWc) / 2;
            const h = (val / maxCost) * chartH;
            ctx.fillStyle = "rgba(6,182,212,0.35)";
            ctx.fillRect(x0, H - botPad - h, barWc, h);
          }
          // Connecting line
          ctx.beginPath();
          ctx.strokeStyle = "#06b6d4"; ctx.lineWidth = 1.2;
          for (let i = 0; i < costDates.length; i++) {
            const di = dates.indexOf(costDates[i]);
            const val = costByDate[costDates[i]];
            const x = leftPad + di * ((W - leftPad - 2) / dates.length) + (W-leftPad-2)/dates.length/2;
            const y = H - botPad - (val / maxCost) * chartH;
            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
          }
          ctx.stroke();
        }

        // Date labels (sparse)
        dates.forEach((date: string, di: number) => {
          if (dates.length <= 14 || di % 3 === 0) {
            ctx.fillStyle = "#64748b"; ctx.font = "7px monospace";
            ctx.fillText(date.slice(5), leftPad + di * ((W - leftPad - 2) / dates.length), H - 2);
          }
        });
      }
    }
    // Compute 30-day totals
    const proRows = rows.filter((r: any) => r.model === "deepseek-v4-pro");
    const flashRows = rows.filter((r: any) => r.model === "deepseek-v4-flash");
    dsTotals.value = {
      pro: proRows.reduce((s: number, r: any) => s + (r.input_cache_miss||0) + (r.output_tokens||0) + (r.input_cache_hit||0), 0),
      flash: flashRows.reduce((s: number, r: any) => s + (r.input_cache_miss||0) + (r.output_tokens||0) + (r.input_cache_hit||0), 0),
      cost: rows.reduce((s: number, r: any) => s + (r.cost_cny||0), 0),
    };
  } catch (e) { /* silent */ }
}

onMounted(() => {
  fetchData();
  timer = window.setInterval(fetchData, 10_000);
  elapTimer = window.setInterval(() => { elapsed.value = Math.round((Date.now() - lastFetch.value) / 1000); }, 1000);
});
onUnmounted(() => { if (timer) clearInterval(timer); if (elapTimer) clearInterval(elapTimer); });
</script>

<style scoped>
.monitor-page { padding: 18px; max-width: 1280px; margin: 0 auto; }
.metric-card { background: var(--glass-bg); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 10px 12px; }
.progress-bar { height: 3px; border-radius: 2px; transition: width 0.5s ease; min-width: 0; }
.load-values { display: flex; gap: 8px; flex-wrap: wrap; }
.tag-badge { font-size: 9px; font-family: \"JetBrains Mono\", monospace; padding: 1px 6px; border-radius: 3px; white-space: nowrap; }
</style>
