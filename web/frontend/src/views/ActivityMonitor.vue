<template>
  <div class="monitor-page">
    <div class="glass-card p-6">
      <div class="flex items-center gap-2 mb-4">
        <span class="text-lg">🖥️</span>
        <h2 class="text-lg font-semibold" style="color:var(--text-primary)">活动监视器</h2>
        <span class="text-2xs px-2 py-0.5 rounded" style="background:var(--bg-active);color:var(--text-disabled)">{{ elapsed }}s前</span>
        <button @click="fetchData" class="text-xs px-2 py-1 rounded" style="background:var(--accent);color:#000">刷新</button>
      </div>

      <!-- CPU + Memory + Disk row -->
      <div class="grid grid-cols-3 gap-3 mb-4">
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
      <div class="grid grid-cols-2 gap-3 mb-4">
        <div class="metric-card">
          <div class="text-2xs" style="color:var(--text-disabled)">电池</div>
          <div class="flex items-center gap-1">
            <span class="text-lg">{{ data?.battery?.charging ? '⚡' : '🔋' }}</span>
            <span class="text-xl font-mono font-bold" style="color:var(--positive)">{{ data?.battery?.percent ?? '—' }}%</span>
          </div>
        </div>
        <div class="metric-card">
          <div class="text-2xs" style="color:var(--text-disabled)">系统负载</div>
          <div class="text-sm font-mono" style="color:var(--text-secondary)">
            <span v-for="(l, i) in data?.cpu.load_avg ?? []" :key="i" class="mr-2">{{ l }}</span>
          </div>
        </div>
      </div>

      <!-- Token Usage -->
      <div class="metric-card p-4 mb-4" style="border-left:2px solid var(--accent)">
        <div class="text-2xs mb-2" style="color:var(--text-disabled)">今日 Token 用量</div>
        <div class="grid grid-cols-2 gap-4">
          <div>
            <div class="text-2xs" style="color:var(--text-disabled)">Hermes 会话</div>
            <div class="text-xs font-mono mt-0.5" style="color:var(--text-secondary)">
              📥 {{ fmtNum(data?.token?.hermes?.input_tokens ?? 0) }}  📤 {{ fmtNum(data?.token?.hermes?.output_tokens ?? 0) }}
            </div>
            <div class="text-2xs" style="color:var(--accent)">${{ (data?.token?.hermes?.cost_usd ?? 0).toFixed(4) }}</div>
          </div>
          <div>
            <div class="text-2xs" style="color:var(--text-disabled)">
              外部调用 <span v-if="(data?.token?.external?.sources ?? []).length">({{ data?.token?.external?.sources?.join(', ') }})</span>
            </div>
            <div class="text-xs font-mono mt-0.5" :style="{color: (data?.token?.external?.input_tokens ?? 0) > 0 ? 'var(--text-secondary)' : 'var(--text-disabled)'}">
              📥 {{ fmtNum(data?.token?.external?.input_tokens ?? 0) }}  📤 {{ fmtNum(data?.token?.external?.output_tokens ?? 0) }}
            </div>
            <div class="text-2xs" :style="{color: (data?.token?.external?.cost_usd ?? 0) > 0 ? 'var(--accent)' : 'var(--text-disabled)'}">
              ${{ (data?.token?.external?.cost_usd ?? 0).toFixed(4) }} ({{ data?.token?.external?.calls ?? 0 }} calls)
            </div>
          </div>
        </div>
        <div class="mt-2 pt-2 flex justify-between" style="border-top:1px solid var(--border-subtle)">
          <span class="text-xs font-bold" style="color:var(--text-primary)">合计 ${{ (data?.token?.total?.cost_usd ?? 0).toFixed(4) }}</span>
          <span class="text-2xs" style="color:var(--text-disabled)">
            📥 {{ fmtNum(data?.token?.total?.input_tokens ?? 0) }} 📤 {{ fmtNum(data?.token?.total?.output_tokens ?? 0) }}
          </span>
        </div>
      </div>

      <!-- Top Processes -->
      <div>
        <div class="text-2xs mb-2" style="color:var(--text-disabled)">高占用进程</div>
        <table class="w-full text-xs">
          <thead><tr style="color:var(--text-disabled)"><th class="text-left font-normal">进程</th><th class="text-right font-normal w-16">CPU</th><th class="text-right font-normal w-16">内存</th></tr></thead>
          <tbody>
            <tr v-for="p in data?.top_processes ?? []" :key="p.pid" class="border-t" style="border-color:var(--border-subtle)">
              <td class="py-1 font-mono" style="color:var(--text-secondary)">{{ p.name }}</td>
              <td class="py-1 text-right font-mono" style="color:var(--text-secondary)">{{ p.cpu }}%</td>
              <td class="py-1 text-right font-mono" style="color:var(--text-secondary)">{{ p.mem }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- History Charts -->
    <div class="glass-card p-6 mt-4">
      <h3 class="text-sm font-semibold mb-3" style="color:var(--text-primary)">历史趋势 ({{ historyHours }}h)</h3>
      <div class="grid grid-cols-3 gap-4">
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

function fmtNum(n: number): string {
  if (n > 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n > 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

async function fetchData() {
  try {
    data.value = await api.systemMonitor();
    lastFetch.value = Date.now();
    drawCharts();
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

onMounted(() => {
  fetchData();
  timer = window.setInterval(fetchData, 10_000);
  elapTimer = window.setInterval(() => { elapsed.value = Math.round((Date.now() - lastFetch.value) / 1000); }, 1000);
});
onUnmounted(() => { if (timer) clearInterval(timer); if (elapTimer) clearInterval(elapTimer); });
</script>

<style scoped>
.monitor-page { padding: 24px; max-width: 800px; margin: 0 auto; }
.metric-card { background: var(--glass-bg); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 10px 12px; }
.progress-bar { height: 3px; border-radius: 2px; transition: width 0.5s ease; min-width: 0; }
</style>
