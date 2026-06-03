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
          @click="activeGroup = group.key"
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

        <div class="subgroup-stack">
          <section v-for="subgroup in groupedSections" :key="subgroup.key" class="config-subgroup">
            <div class="subgroup-header">
              <h4>{{ subgroup.label }}</h4>
              <span>{{ t('configCenter.subgroupSummary', { count: subgroup.sections.length }) }}</span>
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
                  <div class="field-input-wrap">
                    <label v-if="field.type === 'bool'" class="field-switch">
                      <input type="checkbox" :checked="!!getFieldValue(section.key, field.key)" @change="setFieldValue(section.key, field.key, ($event.target as HTMLInputElement).checked)" />
                      <span></span>
                    </label>
                    <select v-else-if="field.type === 'select'" class="field-select" :value="getFieldValue(section.key, field.key)" @change="setFieldValue(section.key, field.key, ($event.target as HTMLSelectElement).value)">
                      <option v-for="option in field.options" :key="option.value ?? option" :value="option.value ?? option">{{ option.label ?? option }}</option>
                    </select>
                    <input v-else-if="field.type === 'string'" type="text" class="field-input field-input-wide" :value="getFieldValue(section.key, field.key)" :placeholder="String(field.default ?? '')" @input="setFieldValue(section.key, field.key, ($event.target as HTMLInputElement).value)" />
                    <template v-else-if="field.min !== undefined && field.max !== undefined">
                      <input type="range" class="field-slider" :min="field.min" :max="field.max" :step="field.type === 'int' ? 1 : (field.max - field.min) / 100" :value="getFieldValue(section.key, field.key) ?? field.default ?? 0" @input="onSliderInput(section.key, field, $event)" />
                      <input type="number" class="field-input field-input-small" :step="field.type === 'int' ? 1 : 'any'" :value="getFieldValue(section.key, field.key)" :min="field.min" :max="field.max" @input="setFieldValue(section.key, field.key, coerceNumericField(field, $event))" />
                    </template>
                    <input v-else type="number" class="field-input field-input-small" :step="field.type === 'int' ? 1 : 'any'" :value="getFieldValue(section.key, field.key)" :placeholder="String(field.default ?? '')" @input="setFieldValue(section.key, field.key, coerceNumericField(field, $event))" />
                  </div>
                </div>
              </div>

              <div class="section-actions">
                <span v-if="saveMsg && saveMsgSection === section.key" class="save-msg" :class="saveOk ? 'ok' : 'err'">{{ saveMsg }}</span>
                <button class="btn-reset" :disabled="!sectionHasChanges(section.key)" @click="resetSection(section.key)">{{ t('common.reset') }}</button>
                <button class="btn-save" :disabled="!sectionHasChanges(section.key) || isSaving(section.key)" @click="saveSection(section.key)">
                  {{ isSaving(section.key) ? t('common.saving') : t('configCenter.saveChanges') }}
                </button>
              </div>
            </article>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useConfigCenter } from "../view-models/useConfigCenter";

const { groups, t, activeGroup, loading, saveMsgSection, saveMsg, saveOk, activeGroupInfo, groupedSections, getFieldValue, setFieldValue, onSliderInput, coerceNumericField, sectionHasChanges, resetSection, saveSection, isSaving } = useConfigCenter();
</script>

<style scoped src="../styles/views/config-center.css"></style>
