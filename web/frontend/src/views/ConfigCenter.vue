<template>
  <div class="config-center">
    <div v-if="loading" class="config-loading">{{ t('configCenter.loading') }}</div>
    <div v-else class="config-layout">
      <nav class="config-nav">
        <button
          v-for="group in groups"
          :key="group.key"
          class="nav-item"
          :class="{ active: activeGroup === group.key }"
          @click="setActiveGroup(group.key)"
        >
          <span class="nav-copy">
            <span class="nav-label">{{ group.label }}</span>
            <small>{{ group.description }}</small>
          </span>
          <span class="nav-count">{{ group.section_count }}</span>
        </button>
      </nav>

      <div class="config-editor" v-if="activeGroupInfo">
        <div class="editor-header">
          <div>
            <h3>{{ activeGroupInfo.label }}</h3>
            <p>{{ activeGroupInfo.description }}</p>
          </div>
          <span>{{ t('configCenter.sectionSummary', { sections: activeGroupInfo.section_count, fields: activeGroupInfo.field_count }) }}</span>
        </div>

        <div class="config-body" :class="{ 'has-strategy-nav': strategyNavItems.length }">
          <aside v-if="strategyNavItems.length" class="strategy-subnav" data-strategy-subnav :aria-label="t('configCenter.strategyQuickNav')">
            <div class="strategy-subnav-title">
              <span>{{ t('configCenter.strategyQuickNav') }}</span>
              <small>{{ strategyNavItems.length }}</small>
            </div>
            <button
              v-for="item in strategyNavItems"
              :key="item.key"
              class="strategy-subnav-item"
              :class="{ active: visibleSubgroupKey === item.key }"
              :title="navButtonTitle(item)"
              @click="jumpToSubgroup(item.key)"
            >
              <span class="strategy-subnav-label">
                <i
                  v-if="item.enabled !== null"
                  class="strategy-status-dot"
                  :class="item.enabled ? 'enabled' : 'disabled'"
                  :title="strategyStatusLabel(item)"
                  aria-hidden="true"
                ></i>
                <span>{{ item.label }}</span>
              </span>
              <small>{{ navItemMeta(item) }}</small>
            </button>
          </aside>

          <div ref="editorScrollRef" class="subgroup-stack">
          <section
            v-for="subgroup in groupedSections"
            :id="subgroupDomId(subgroup.key)"
            :key="subgroup.key"
            class="config-subgroup"
            :data-config-subgroup="subgroup.key"
          >
            <div class="subgroup-header">
              <h4>{{ subgroup.label }}</h4>
              <span>{{ subgroupMeta(subgroup.sections) }}</span>
            </div>

            <article v-for="section in subgroup.sections" :key="section.key" class="section-panel">
              <div class="section-header">
                <div>
                  <h5>{{ section.label }}</h5>
                  <p>{{ section.description }}</p>
                </div>
                <code>{{ section.key }}</code>
              </div>

              <div class="field-grid">
                <div v-for="field in section.fields" :key="field.key" class="field-row">
                  <div class="field-info">
                    <span class="field-type" :class="`type-${field.type}`">{{ field.type }}</span>
                    <span class="field-label">{{ field.label }}</span>
                  </div>
                  <div class="field-hints">
                    <span class="field-range" v-if="field.min !== undefined || field.max !== undefined">{{ field.min ?? '—' }} ~ {{ field.max ?? '—' }}</span>
                    <span class="field-default" v-if="field.default !== undefined">{{ t('configCenter.defaultValue', { value: field.default }) }}</span>
                  </div>
                  <div class="field-readonly-wrap">
                    <span
                      class="field-readonly-value"
                      :class="fieldValueClass(section.key, field)"
                    >
                      {{ displayFieldValue(section.key, field) }}
                    </span>
                  </div>
                </div>
              </div>
            </article>
          </section>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useConfigCenter } from "../view-models/useConfigCenter";

const { groups, t, activeGroup, loading, editorScrollRef, activeGroupInfo, groupedSections, strategyNavItems, visibleSubgroupKey, setActiveGroup, jumpToSubgroup, subgroupDomId, navItemMeta, strategyStatusLabel, navButtonTitle, subgroupMeta, displayFieldValue, fieldValueClass } = useConfigCenter();
</script>

<style scoped src="../styles/views/config-center.css"></style>
