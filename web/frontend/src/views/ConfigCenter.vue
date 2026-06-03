<template>
  <div class="config-center">
    <div v-if="loading" class="config-loading">{{ t('configCenter.loading') }}</div>
    <div v-else class="config-layout">
      <!-- Left: section list -->
      <nav class="config-nav">
        <button
          v-for="section in schema"
          :key="section.key"
          class="nav-item"
          :class="{ active: activeSection === section.key }"
          @click="activeSection = section.key"
        >
          <span class="nav-label">{{ section.label }}</span>
          <span class="nav-count">{{ section.fields.length }}</span>
        </button>
      </nav>

      <!-- Right: field editor -->
      <div class="config-editor" v-if="currentSection">
        <div class="editor-header">
          <h3>{{ currentSection.label }}</h3>
          <p>{{ currentSection.description }}</p>
        </div>

        <div class="field-grid">
          <div v-for="field in currentSection.fields" :key="field.key" class="field-card">
            <div class="field-info">
              <span class="field-type" :class="`type-${field.type}`">{{ field.type }}</span>
              <span class="field-label">{{ field.label }}</span>
            </div>
            <div class="field-hints">
              <span class="field-range" v-if="field.min !== undefined || field.max !== undefined">
                {{ field.min ?? '—' }} ~ {{ field.max ?? '—' }}
              </span>
              <span class="field-default" v-if="field.default !== undefined">
                {{ t('configCenter.defaultValue', { value: field.default }) }}
              </span>
            </div>
            <div class="field-input-wrap">
              <!-- string: text input only -->
              <input
                v-if="field.type === 'string'"
                type="text"
                class="field-input field-input-wide"
                :value="getFieldValue(field.key)"
                :placeholder="String(field.default ?? '')"
                @input="setFieldValue(field.key, ($event.target as HTMLInputElement).value)"
              />
              <!-- int/float with range: slider + input -->
              <template v-else-if="field.min !== undefined && field.max !== undefined">
                <input
                  type="range"
                  class="field-slider"
                  :min="field.min"
                  :max="field.max"
                  :step="field.type === 'int' ? 1 : (field.max - field.min) / 100"
                  :value="getFieldValue(field.key) ?? field.default ?? 0"
                  @input="onSliderInput(field, $event)"
                />
                <input
                  type="number"
                  class="field-input field-input-small"
                  :step="field.type === 'int' ? 1 : 'any'"
                  :value="getFieldValue(field.key)"
                  :min="field.min"
                  :max="field.max"
                  @input="setFieldValue(field.key, field.type === 'int' ? parseInt(($event.target as HTMLInputElement).value) : parseFloat(($event.target as HTMLInputElement).value))"
                />
              </template>
              <!-- int/float without range: input only -->
              <input
                v-else
                type="number"
                class="field-input field-input-small"
                :step="field.type === 'int' ? 1 : 'any'"
                :value="getFieldValue(field.key)"
                :placeholder="String(field.default ?? '')"
                @input="setFieldValue(field.key, field.type === 'int' ? parseInt(($event.target as HTMLInputElement).value) : parseFloat(($event.target as HTMLInputElement).value))"
              />
            </div>
          </div>
        </div>

        <div class="editor-actions">
          <button
            class="btn-save"
            :disabled="!hasChanges || saving"
            @click="saveSection"
          >
            {{ saving ? t('common.saving') : t('configCenter.saveChanges') }}
          </button>
          <button
            class="btn-reset"
            :disabled="!hasChanges"
            @click="resetSection"
          >
            {{ t('common.reset') }}
          </button>
          <span v-if="saveMsg" class="save-msg" :class="saveOk ? 'ok' : 'err'">{{ saveMsg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useConfigCenter } from "../view-models/useConfigCenter";

const { schema, t, config, originalConfig, activeSection, loading, saving, saveMsg, saveOk, currentSection, hasChanges, getNestedValue, setNestedValue, getSectionData, getFieldValue, setFieldValue, onSliderInput, resetSection, saveSection } = useConfigCenter();
</script>

<style scoped src="../styles/views/config-center.css"></style>
