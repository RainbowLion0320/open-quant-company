<template>
  <div class="view-page module-page">
    <SectionTabs
      title="策略实验室"
      eyebrow="Strategy Lab"
      subtitle="策略运行、信号变化和回测表现合并为完整研究闭环"
      base-path="/strategy-lab"
      default-tab="strategies"
      :items="tabs"
    />
    <section class="module-content">
      <component :is="activeComponent" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import SectionTabs from "../components/SectionTabs.vue";
import Strategies from "./Strategies.vue";
import Signals from "./Signals.vue";
import Backtest from "./Backtest.vue";

const route = useRoute();

const tabs = [
  { key: "strategies", label: "策略中心", meta: "Run & inspect", description: "查看四类策略状态、运行扫描，并下钻最新候选信号" },
  { key: "signals", label: "信号历史", meta: "Signal changes", description: "追踪最近信号迁移，识别新增买入、降级和策略一致性变化" },
  { key: "backtest", label: "回测分析", meta: "Tournament", description: "对比策略收益、风险、回撤和相对上证基准表现" },
];

const activeTab = computed(() => {
  const tab = typeof route.query.tab === "string" ? route.query.tab : "";
  return tabs.some(item => item.key === tab) ? tab : "strategies";
});

const componentMap = {
  strategies: Strategies,
  signals: Signals,
  backtest: Backtest,
};

const activeComponent = computed(() => componentMap[activeTab.value as keyof typeof componentMap] || Strategies);
</script>

<style scoped>
.module-page {
  gap: 14px;
}

.module-content {
  min-width: 0;
}

.module-content :deep(.view-page) {
  padding: 0;
}
</style>
