<template>
  <div class="p-6 space-y-5">
    <div class="page-header">
      <div>
        <h1 class="page-title">个股深挖</h1>
        <p class="page-subtitle">搜索股票代码或名称 · 查看基本面与信号</p>
      </div>
    </div>

    <!-- Search -->
    <div class="glass-card" style="padding:16px">
      <div class="flex gap-3">
        <input
          v-model="query"
          type="search"
          placeholder="输入代码或名称，如 600519 或 茅台"
          class="flex-1"
          @keydown.enter="search"
        />
        <button @click="search" class="btn btn-primary">搜索</button>
      </div>
    </div>

    <!-- Result -->
    <div v-if="stock" class="glass-card glow-cyan animate-fade-in" style="padding:20px">
      <!-- Basic Info -->
      <div class="flex items-center gap-3 mb-4">
        <div class="text-xl font-bold font-mono" style="color:var(--accent)">{{ stock.basic.symbol }}</div>
        <div class="text-lg font-semibold" style="color:var(--text-primary)">{{ stock.basic.name }}</div>
        <div class="badge" :class="marketBadge">{{ stock.basic.market }}</div>
      </div>

      <div class="grid grid-cols-4 gap-3 mb-4 text-xs">
        <div>
          <span style="color:var(--text-disabled)">行业</span>
          <div class="mt-0.5" style="color:var(--text-secondary)">{{ stock.basic.industry || '—' }}</div>
        </div>
        <div>
          <span style="color:var(--text-disabled)">地区</span>
          <div class="mt-0.5" style="color:var(--text-secondary)">{{ stock.basic.area || '—' }}</div>
        </div>
      </div>

      <!-- Buffett Score -->
      <div v-if="stock.buffett" class="grid grid-cols-5 gap-3 p-3 rounded-lg mb-4" style="background:var(--bg-deep)">
        <div class="text-center">
          <div class="text-[10px]" style="color:var(--text-disabled)">巴菲特分</div>
          <div class="text-lg font-bold font-mono mt-1" :style="{ color: (stock.buffett.score||0) >= 70 ? 'var(--positive)' : 'var(--warning)' }">
            {{ stock.buffett.score?.toFixed(0) || '—' }}
          </div>
        </div>
        <div class="text-center">
          <div class="text-[10px]" style="color:var(--text-disabled)">ROE</div>
          <div class="text-sm font-mono mt-1" style="color:var(--text-secondary)">{{ fmtPct(stock.buffett.roe) }}</div>
        </div>
        <div class="text-center">
          <div class="text-[10px]" style="color:var(--text-disabled)">毛利率</div>
          <div class="text-sm font-mono mt-1" style="color:var(--text-secondary)">{{ fmtPct(stock.buffett.gross_margin) }}</div>
        </div>
        <div class="text-center">
          <div class="text-[10px]" style="color:var(--text-disabled)">D/E</div>
          <div class="text-sm font-mono mt-1" style="color:var(--text-secondary)">{{ stock.buffett.debt_equity?.toFixed(2) || '—' }}</div>
        </div>
        <div class="text-center">
          <div class="text-[10px]" style="color:var(--text-disabled)">DCF 估值</div>
          <div class="text-sm font-mono mt-1" style="color:var(--text-secondary)">{{ stock.buffett.dcf_value?.toFixed(2) || '—' }}</div>
        </div>
      </div>

      <!-- Signals -->
      <div v-if="stock.signals && Object.keys(stock.signals).length">
        <div class="text-xs font-semibold mb-3" style="color:var(--text-tertiary)">策略信号</div>
        <table class="data-table">
          <thead>
            <tr><th style="width:40%">策略</th><th style="width:30%" class="text-right">评分</th><th style="width:30%" class="text-right">信号</th></tr>
          </thead>
          <tbody>
            <tr v-for="(sigs, strategy) in stock.signals" :key="strategy">
              <td style="color:var(--text-secondary)">{{ strategy }}</td>
              <td class="text-right font-mono">{{ sigs[0]?.score?.toFixed(1) || '—' }}</td>
              <td class="text-right">
                <span :style="{ color: sigs[0]?.signal === 'buy' ? 'var(--positive)' : 'var(--text-disabled)' }">
                  {{ sigs[0]?.signal === 'buy' ? '买入' : '持有' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <router-link :to="`/stocks/${stock.basic.symbol}`" class="btn btn-sm mt-4" style="border-color:rgba(0,212,255,0.2); color:var(--accent)">
        查看详细
      </router-link>
    </div>

    <div v-else-if="searched && !stock" class="empty-state">
      未找到该股票
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { api } from "../api";
import type { StockDetail } from "../api";

const query = ref("");
const stock = ref<StockDetail | null>(null);
const searched = ref(false);

function fmtPct(v: number | undefined) { return v != null ? (v * 100).toFixed(1) + "%" : "—"; }

const marketBadge = computed(() => {
  const m = stock.value?.basic.market;
  if (m === "主板") return "badge-green";
  if (m === "创业板") return "badge-amber";
  if (m === "科创板") return "badge-red";
  return "";
});

async function search() {
  if (!query.value.trim()) return;
  searched.value = true;
  try {
    stock.value = await api.stock(query.value.trim());
  } catch { stock.value = null; }
}
</script>
