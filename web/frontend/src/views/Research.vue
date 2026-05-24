<template>
  <div class="view-page module-page">
    <SectionTabs
      title="市场研究"
      eyebrow="Research"
      subtitle="行业轮动、个股搜索和标的深挖集中在一个研究入口"
      base-path="/research"
      default-tab="sectors"
      :items="tabs"
      :show-copy="false"
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
import Sectors from "./Sectors.vue";
import Stocks from "./Stocks.vue";

const route = useRoute();

const tabs = [
  { key: "sectors", label: "行业雷达", meta: "Sector rotation" },
  { key: "stocks", label: "个股搜索", meta: "Stock research" },
];

const activeTab = computed(() => {
  const tab = typeof route.query.tab === "string" ? route.query.tab : "";
  return tabs.some(item => item.key === tab) ? tab : "sectors";
});

const activeComponent = computed(() => activeTab.value === "stocks" ? Stocks : Sectors);
</script>

<style scoped>
.module-page {
  gap: 8px;
  padding-top: 10px;
}

.module-content {
  min-width: 0;
}

.module-content :deep(.view-page) {
  padding: 0;
}
</style>
