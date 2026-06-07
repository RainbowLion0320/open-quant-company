<template>
  <div class="view-page module-page">
    <SectionTabs
      :title="t('modules.system.title')"
      :eyebrow="t('modules.system.eyebrow')"
      :subtitle="t('modules.system.subtitle')"
      base-path="/system"
      default-tab="monitor"
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
import ActivityMonitor from "./ActivityMonitor.vue";
import Settings from "./Settings.vue";
import ConfigCenter from "./ConfigCenter.vue";
import TestDesign from "./TestDesign.vue";
import CodeGraph from "./CodeGraph.vue";

const { t } = useI18n();

const tabKeys = [
  { key: "monitor" },
  { key: "settings" },
  { key: "config" },
  { key: "tests" },
  { key: "codegraph" },
];

const tabs = computed(() => tabKeys.map(item => ({
  key: item.key,
  label: t(`modules.system.tabs.${item.key}.label`),
  meta: t(`modules.system.tabs.${item.key}.meta`),
  description: t(`modules.system.tabs.${item.key}.description`),
})));

const { activeComponent } = useModuleTabs(tabKeys, "monitor", {
  monitor: ActivityMonitor,
  settings: Settings,
  config: ConfigCenter,
  tests: TestDesign,
  codegraph: CodeGraph,
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
