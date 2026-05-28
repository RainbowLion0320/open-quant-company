<template>
  <div class="view-page module-page">
    <SectionTabs
      title="策略实验室"
      eyebrow="Strategy Lab"
      subtitle="策略目录、信号变化和回测证据合并为完整研究闭环"
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
import SectionTabs from "../components/SectionTabs.vue";
import { useModuleTabs } from "../composables/useModuleTabs";
import Strategies from "./Strategies.vue";
import Signals from "./Signals.vue";
import Backtest from "./Backtest.vue";

const tabs = [
  { key: "strategies", label: "策略目录", meta: "Catalog & gates", description: "查看生产策略和候选策略目录、生命周期、研究扫描与生产隔离状态" },
  { key: "signals", label: "信号历史", meta: "Signal changes", description: "追踪最近信号迁移，识别新增买入、降级和策略一致性变化" },
  { key: "backtest", label: "回测证据", meta: "Evidence", description: "对比策略收益、风险、回撤、强基准和晋级证据" },
];

const { activeComponent } = useModuleTabs(tabs, "strategies", {
  strategies: Strategies,
  signals: Signals,
  backtest: Backtest,
});
</script>

<style scoped>
.module-page {
  gap: 10px;
  padding-top: 10px;
}

.module-content {
  min-width: 0;
}

.module-content :deep(.view-page) {
  padding: 0;
}
</style>
