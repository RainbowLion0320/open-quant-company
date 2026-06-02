<template>
  <div class="view-page module-page">
    <SectionTabs
      :title="t('modules.datahub.title')"
      :eyebrow="t('modules.datahub.eyebrow')"
      :subtitle="t('modules.datahub.subtitle')"
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
import { computed } from "vue";
import SectionTabs from "../components/SectionTabs.vue";
import { useModuleTabs } from "../composables/useModuleTabs";
import { useI18n } from "../i18n";
import DatabaseHealth from "./DatabaseHealth.vue";
import AssetCoverage from "./AssetCoverage.vue";

const { t } = useI18n();

const tabKeys = [
  { key: "health" },
  { key: "assets" },
];

const tabs = computed(() => tabKeys.map(item => ({
  key: item.key,
  label: t(`modules.datahub.tabs.${item.key}.label`),
  meta: t(`modules.datahub.tabs.${item.key}.meta`),
  description: t(`modules.datahub.tabs.${item.key}.description`),
})));

const { activeComponent } = useModuleTabs(tabKeys, "health", {
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
