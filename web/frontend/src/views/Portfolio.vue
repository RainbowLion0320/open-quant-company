<template>
  <div class="p-6 space-y-5">
    <div class="page-header">
      <div>
        <h1 class="page-title">模拟交易</h1>
        <p class="page-subtitle">PaperBroker · T+1 制度 · 实盘成本模拟</p>
      </div>
    </div>

    <!-- Balance Card -->
    <div class="grid grid-cols-4 gap-3">
      <div class="glass-card" style="padding:14px 16px">
        <div class="text-[10px] tracking-wider uppercase" style="color:var(--text-disabled)">总资产</div>
        <div class="text-xl font-bold font-mono mt-1" style="color:var(--accent)">¥{{ balance.total_value?.toLocaleString() || '—' }}</div>
      </div>
      <div class="glass-card" style="padding:14px 16px">
        <div class="text-[10px] tracking-wider uppercase" style="color:var(--text-disabled)">可用现金</div>
        <div class="text-lg font-mono mt-1" style="color:var(--text-secondary)">¥{{ balance.cash?.toLocaleString() || '—' }}</div>
      </div>
      <div class="glass-card" style="padding:14px 16px">
        <div class="text-[10px] tracking-wider uppercase" style="color:var(--text-disabled)">总盈亏</div>
        <div class="text-lg font-bold font-mono mt-1" :style="{ color: (balance.total_pnl||0) >= 0 ? 'var(--positive)' : 'var(--negative)' }">
          {{ fmtPnl(balance.total_pnl) }}
        </div>
      </div>
      <div class="glass-card" style="padding:14px 16px">
        <div class="text-[10px] tracking-wider uppercase" style="color:var(--text-disabled)">收益率</div>
        <div class="text-lg font-bold font-mono mt-1" :style="{ color: (balance.total_pnl_pct||0) >= 0 ? 'var(--positive)' : 'var(--negative)' }">
          {{ fmtPct(balance.total_pnl_pct) }}
        </div>
      </div>
    </div>

    <!-- Positions -->
    <div class="glass-card" style="padding:20px">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">当前持仓</div>
      <table class="data-table" v-if="positions.length">
        <thead>
          <tr>
            <th>代码</th><th>名称</th><th class="text-right">数量</th>
            <th class="text-right">成本</th><th class="text-right">现价</th>
            <th class="text-right">盈亏</th><th class="text-right">比例</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in positions" :key="p.symbol">
            <td class="font-mono">{{ p.symbol }}</td>
            <td>{{ p.name }}</td>
            <td class="text-right font-mono">{{ p.shares }}</td>
            <td class="text-right font-mono">¥{{ p.cost?.toFixed(2) }}</td>
            <td class="text-right font-mono">¥{{ p.price?.toFixed(2) }}</td>
            <td class="text-right font-mono" :style="{ color: (p.pnl||0) >= 0 ? 'var(--positive)' : 'var(--negative)' }">
              {{ fmtPnl(p.pnl) }}
            </td>
            <td class="text-right font-mono" :style="{ color: (p.pnl_pct||0) >= 0 ? 'var(--positive)' : 'var(--negative)' }">
              {{ fmtPct(p.pnl_pct) }}
            </td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-state" style="padding:24px">
        <span>暂无持仓</span>
      </div>
    </div>

    <!-- Order Form -->
    <div class="glass-card" style="padding:20px">
      <div class="text-xs font-semibold tracking-wide mb-4" style="color:var(--text-secondary)">下单</div>
      <div class="flex gap-3 items-end">
        <div class="flex-1">
          <div class="text-[10px] mb-1" style="color:var(--text-disabled)">股票代码</div>
          <input v-model="order.symbol" type="text" placeholder="000001" class="w-full" />
        </div>
        <div style="width:80px">
          <div class="text-[10px] mb-1" style="color:var(--text-disabled)">方向</div>
          <select v-model="order.side" class="w-full">
            <option value="buy">买入</option>
            <option value="sell">卖出</option>
          </select>
        </div>
        <div style="width:100px">
          <div class="text-[10px] mb-1" style="color:var(--text-disabled)">数量</div>
          <input v-model.number="order.shares" type="number" min="100" step="100" class="w-full" />
        </div>
        <button @click="submitOrder" class="btn btn-primary">提交</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue";
import { api } from "../api";
import type { PortfolioPosition, PortfolioBalance } from "../api";

const positions = ref<PortfolioPosition[]>([]);
const balance = ref<PortfolioBalance>({ cash: 0, total_value: 0, total_pnl: 0, total_pnl_pct: 0 });
const order = reactive({ symbol: "", side: "buy" as "buy" | "sell", shares: 100 });

function fmtPnl(v: number | undefined) {
  if (v == null) return "—";
  return (v >= 0 ? "+" : "") + "¥" + Math.abs(v).toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtPct(v: number | undefined) {
  if (v == null) return "—";
  return (v >= 0 ? "+" : "") + (v * 100).toFixed(2) + "%";
}

async function load() {
  try {
    positions.value = await api.portfolioPositions();
    balance.value = await api.portfolioBalance();
  } catch {}
}

async function submitOrder() {
  if (!order.symbol) return;
  try {
    await api.portfolioOrder({ ...order });
    order.symbol = "";
    order.shares = 100;
    await load();
  } catch {}
}

onMounted(load);
</script>
