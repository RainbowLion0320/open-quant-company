<template>
  <header class="section-switcher" :class="{ 'copy-hidden': !showCopy }">
    <div v-if="showCopy" class="section-copy">
      <span>{{ eyebrow }}</span>
      <p>{{ activeDescription }}</p>
    </div>
    <nav class="section-tabs" :aria-label="`${title} tabs`">
      <router-link
        v-for="item in items"
        :key="item.key"
        :to="tabTo(item.key)"
        class="section-tab"
        :class="{ active: activeTab === item.key }"
      >
        <strong>{{ item.label }}</strong>
        <small>{{ item.meta }}</small>
      </router-link>
    </nav>
  </header>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";

interface SectionTabItem {
  key: string;
  label: string;
  meta?: string;
  description?: string;
}

const props = defineProps<{
  title: string;
  subtitle: string;
  eyebrow: string;
  basePath: string;
  defaultTab: string;
  items: SectionTabItem[];
  showCopy?: boolean;
}>();

const route = useRoute();

const activeTab = computed(() => {
  const tab = typeof route.query.tab === "string" ? route.query.tab : "";
  return props.items.some(item => item.key === tab) ? tab : props.defaultTab;
});

const activeItem = computed(() => props.items.find(item => item.key === activeTab.value));
const activeDescription = computed(() => activeItem.value?.description || props.subtitle);
const showCopy = computed(() => props.showCopy !== false);

function tabTo(tab: string) {
  return {
    path: props.basePath,
    query: {
      ...route.query,
      tab,
    },
  };
}
</script>

<style scoped>
.section-switcher {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding: 0 2px 12px;
  border-bottom: 1px solid var(--border-subtle);
}
.section-switcher.copy-hidden {
  align-items: center;
  justify-content: flex-start;
  padding-top: 0;
  padding-bottom: 8px;
}

.section-copy {
  min-width: 260px;
}

.section-copy span {
  display: block;
  color: var(--text-tertiary);
  font-size: 9px;
  font-weight: 650;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.section-copy p {
  margin-top: 6px;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.55;
}

.section-tabs {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
.section-switcher.copy-hidden .section-tabs {
  justify-content: flex-start;
}

.section-tab {
  min-width: 126px;
  padding: 8px 11px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: rgba(8, 19, 33, 0.34);
  color: var(--text-tertiary);
  transition: border-color 0.18s ease, background 0.18s ease, color 0.18s ease, transform 0.18s ease;
}
.section-switcher.copy-hidden .section-tab {
  min-width: 118px;
  padding: 7px 10px;
}

.section-tab:hover {
  color: var(--text-secondary);
  border-color: var(--border-default);
  background: rgba(0, 212, 255, 0.045);
}

.section-tab.active {
  color: var(--accent);
  border-color: rgba(0, 212, 255, 0.3);
  background: linear-gradient(135deg, rgba(0, 212, 255, 0.12), rgba(124, 58, 237, 0.08));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04), 0 0 18px rgba(0, 212, 255, 0.08);
}

.section-tab strong {
  display: block;
  color: currentColor;
  font-size: 12px;
  font-weight: 650;
  line-height: 1.25;
}

.section-tab small {
  display: block;
  margin-top: 3px;
  color: var(--text-disabled);
  font-size: 9px;
  line-height: 1.25;
  white-space: nowrap;
}

@media (max-width: 760px) {
  .section-switcher {
    align-items: stretch;
    flex-direction: column;
  }

  .section-tabs {
    justify-content: flex-start;
  }

  .section-tab {
    flex: 1 1 128px;
  }
}
</style>
