<template>
  <div class="view-page module-page">
    <SectionTabs
      title="系统控制"
      eyebrow="System"
      subtitle="运行观测、配置写入和 AI 记忆工具收敛为系统入口"
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
import { useRoute } from "vue-router";
import SectionTabs from "../components/SectionTabs.vue";
import ActivityMonitor from "./ActivityMonitor.vue";
import Settings from "./Settings.vue";
import HindsightGraph from "./HindsightGraph.vue";

const route = useRoute();

const tabs = [
  { key: "monitor", label: "系统信息", meta: "Read-only ops", description: "只读观测系统资源、API 健康、任务计划和服务状态" },
  { key: "settings", label: "系统设置", meta: "Config writes", description: "集中管理运行模式、认证、通知、数据源、策略状态和风控参数" },
  { key: "hindsight", label: "记忆图谱", meta: "AI memory", description: "加载 Hindsight 记忆节点，检查经验、观察和实体关系" },
];

const activeTab = computed(() => {
  const tab = typeof route.query.tab === "string" ? route.query.tab : "";
  return tabs.some(item => item.key === tab) ? tab : "monitor";
});

const componentMap = {
  monitor: ActivityMonitor,
  settings: Settings,
  hindsight: HindsightGraph,
};

const activeComponent = computed(() => componentMap[activeTab.value as keyof typeof componentMap] || ActivityMonitor);
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
