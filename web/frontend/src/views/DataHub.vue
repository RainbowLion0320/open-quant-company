<template>
  <div class="view-page module-page">
    <SectionTabs
      title="数据中台"
      eyebrow="DataHub"
      subtitle="数据注册表、健康扫描和修复动作收敛到统一入口"
      base-path="/datahub"
      default-tab="health"
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
import DatabaseHealth from "./DatabaseHealth.vue";
import AssetCoverage from "./AssetCoverage.vue";

const tabs = [
  { key: "health", label: "健康扫描", meta: "Registry health", description: "按表检查新鲜度、缺失、异常和可修复数据维度" },
  { key: "assets", label: "资产覆盖", meta: "Asset coverage", description: "查看多资产数据来源、研究就绪度和交易能力" },
];

const { activeComponent } = useModuleTabs(tabs, "health", {
  health: DatabaseHealth,
  assets: AssetCoverage,
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
