<template>
  <div class="p-6 space-y-6">
    <h1 class="text-lg font-semibold text-white/90">模拟交易</h1>
    <div class="grid grid-cols-4 gap-4">
      <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
        <div class="text-xs text-white/40">总资产</div>
        <div class="text-xl font-semibold tabular-nums">¥{{ balance?.total_asset?.toLocaleString() || '-' }}</div>
      </div>
      <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
        <div class="text-xs text-white/40">可用资金</div>
        <div class="text-lg font-semibold tabular-nums">¥{{ balance?.cash?.toLocaleString() || '-' }}</div>
      </div>
      <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
        <div class="text-xs text-white/40">持仓市值</div>
        <div class="text-lg font-semibold tabular-nums">¥{{ balance?.market_value?.toLocaleString() || '-' }}</div>
      </div>
      <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
        <div class="text-xs text-white/40">持仓数</div>
        <div class="text-lg font-semibold">{{ positions.length }} 只</div>
      </div>
    </div>

    <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
      <h2 class="text-sm font-medium text-white/60 mb-4">下单</h2>
      <div class="flex gap-3 items-end">
        <div class="flex-1"><input v-model="order.code" placeholder="股票代码" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm" /></div>
        <div class="w-24"><input v-model.number="order.price" placeholder="价格" type="number" step="0.01" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm" /></div>
        <div class="w-24"><input v-model.number="order.volume" placeholder="数量" type="number" step="100" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-sm" /></div>
        <select v-model="order.side" class="bg-white/5 border border-white/10 rounded px-3 py-2 text-sm">
          <option value="buy">买入</option>
          <option value="sell">卖出</option>
        </select>
        <button @click="submitOrder" class="px-6 py-2 text-sm rounded bg-[#7170ff] hover:bg-[#8b8aff]">下单</button>
      </div>
    </div>

    <div class="bg-[#111214] border border-white/5 rounded-lg p-4">
      <h2 class="text-sm font-medium text-white/60 mb-4">持仓</h2>
      <table class="w-full text-xs">
        <thead><tr class="text-white/40 border-b border-white/5"><th class="text-left py-2 pr-4">代码</th><th class="text-right py-2 pr-4">持仓</th><th class="text-right py-2 pr-4">成本</th><th class="text-right py-2 pr-4">现价</th><th class="text-right py-2 pr-4">市值</th><th class="text-right py-2">盈亏</th></tr></thead>
        <tbody>
          <tr v-for="p in positions" :key="p.code" class="border-b border-white/[0.02]"><td class="py-2 pr-4 font-mono text-white/50">{{ p.code }}</td><td class="py-2 pr-4 text-right font-mono">{{ p.volume }}</td><td class="py-2 pr-4 text-right font-mono">¥{{ p.avg_cost?.toFixed(2) }}</td><td class="py-2 pr-4 text-right font-mono">¥{{ p.current_price?.toFixed(2) }}</td><td class="py-2 pr-4 text-right font-mono">¥{{ p.market_value?.toLocaleString() }}</td><td class="py-2 text-right font-mono" :class="p.pnl >= 0 ? 'text-green-400' : 'text-red-400'">{{ (p.pnl_pct * 100).toFixed(2) }}%</td></tr>
          <tr v-if="!positions.length"><td colspan="6" class="py-8 text-center text-white/30">暂无持仓</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from "vue";
const positions = ref<any[]>([]);
const balance = ref<any>({});
const order = reactive({ code: "", price: 0, volume: 100, side: "buy" });

async function fetchData() {
  const [pos, bal] = await Promise.all([fetch("/api/portfolio/positions"), fetch("/api/portfolio/balance")]);
  positions.value = await pos.json();
  balance.value = await bal.json();
}

async function submitOrder() {
  await fetch("/api/portfolio/order", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(order),
  });
  order.code = ""; order.price = 0;
  await fetchData();
}

onMounted(fetchData);
</script>
