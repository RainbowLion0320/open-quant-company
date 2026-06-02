import { computed, type Component } from "vue";
import { useRoute } from "vue-router";

export interface ModuleTab {
  key: string;
  label?: string;
  meta?: string;
  description?: string;
}

export function useModuleTabs<T extends string>(
  tabs: readonly ModuleTab[],
  defaultTab: T,
  components: Record<string, Component>,
) {
  const route = useRoute();
  const activeTab = computed(() => {
    const tab = typeof route.query.tab === "string" ? route.query.tab : "";
    return tabs.some(item => item.key === tab) ? tab : defaultTab;
  });
  const activeComponent = computed(() => components[activeTab.value] || components[defaultTab]);
  return { activeTab, activeComponent };
}
