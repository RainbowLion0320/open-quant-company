<template>
  <div class="view-page module-page">
    <SectionTabs
      :title="t('modules.research.title')"
      :eyebrow="t('modules.research.eyebrow')"
      :subtitle="t('modules.research.subtitle')"
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
import SectionTabs from "../components/SectionTabs.vue";
import { useModuleTabs } from "../composables/useModuleTabs";
import { useI18n } from "../i18n";
import Sectors from "./Sectors.vue";
import Stocks from "./Stocks.vue";

const { t } = useI18n();

const tabKeys = [
  { key: "sectors" },
  { key: "stocks" },
];

const tabs = computed(() => tabKeys.map(item => ({
  key: item.key,
  label: t(`modules.research.tabs.${item.key}.label`),
  meta: t(`modules.research.tabs.${item.key}.meta`),
})));

const { activeComponent } = useModuleTabs(tabKeys, "sectors", {
  sectors: Sectors,
  stocks: Stocks,
});
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
