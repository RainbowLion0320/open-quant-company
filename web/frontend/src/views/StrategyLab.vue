<template>
  <div class="view-page module-page">
    <SectionTabs
      :title="t('modules.strategyLab.title')"
      :eyebrow="t('modules.strategyLab.eyebrow')"
      :subtitle="t('modules.strategyLab.subtitle')"
      base-path="/strategy-lab"
      default-tab="strategies"
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
import Strategies from "./Strategies.vue";
import Signals from "./Signals.vue";
import Backtest from "./Backtest.vue";
import StrategyEvidence from "./StrategyEvidence.vue";
import StrategyDataCoverage from "./StrategyDataCoverage.vue";

const { t } = useI18n();

const tabKeys = [
  { key: "strategies" },
  { key: "signals" },
  { key: "backtest" },
  { key: "evidence" },
  { key: "dataCoverage" },
];

const tabs = computed(() => tabKeys.map(item => ({
  key: item.key,
  label: t(`modules.strategyLab.tabs.${item.key}.label`),
  meta: t(`modules.strategyLab.tabs.${item.key}.meta`),
  description: t(`modules.strategyLab.tabs.${item.key}.description`),
})));

const { activeComponent } = useModuleTabs(tabKeys, "strategies", {
  strategies: Strategies,
  signals: Signals,
  backtest: Backtest,
  evidence: StrategyEvidence,
  dataCoverage: StrategyDataCoverage,
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
