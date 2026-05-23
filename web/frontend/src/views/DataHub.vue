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
      <DatabaseHealth />
    </section>
  </div>
</template>

<script setup lang="ts">
import SectionTabs from "../components/SectionTabs.vue";
import DatabaseHealth from "./DatabaseHealth.vue";

const tabs = [
  { key: "health", label: "健康扫描", meta: "Registry health" },
];
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
