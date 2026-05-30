<template>
  <div class="config-center">
    <div v-if="loading" class="config-loading">加载配置 schema...</div>
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
              <span class="field-label">{{ field.label }}</span>
              <span class="field-type" :class="`type-${field.type}`">{{ field.type }}</span>
              <span class="field-range" v-if="field.min !== undefined || field.max !== undefined">
                {{ field.min ?? '—' }} ~ {{ field.max ?? '—' }}
              </span>
              <span class="field-default" v-if="field.default !== undefined">
                默认 {{ field.default }}
              </span>
            </div>
            <div class="field-input-wrap">
              <input
                v-if="field.type === 'string'"
                type="text"
                class="field-input"
                :value="getFieldValue(field.key)"
                :placeholder="String(field.default ?? '')"
                @input="setFieldValue(field.key, ($event.target as HTMLInputElement).value)"
              />
              <input
                v-else-if="field.type === 'int'"
                type="number"
                step="1"
                class="field-input"
                :value="getFieldValue(field.key)"
                :min="field.min"
                :max="field.max"
                :placeholder="String(field.default ?? '')"
                @input="setFieldValue(field.key, parseInt(($event.target as HTMLInputElement).value))"
              />
              <input
                v-else
                type="number"
                step="any"
                class="field-input"
                :value="getFieldValue(field.key)"
                :min="field.min"
                :max="field.max"
                :placeholder="String(field.default ?? '')"
                @input="setFieldValue(field.key, parseFloat(($event.target as HTMLInputElement).value))"
              />
            </div>
            <p class="field-desc" v-if="field.description">{{ field.description }}</p>
            <p class="field-range" v-if="field.min !== undefined || field.max !== undefined">
              范围: {{ field.min ?? '—' }} ~ {{ field.max ?? '—' }}
            </p>
          </div>
        </div>

        <div class="editor-actions">
          <button
            class="btn-save"
            :disabled="!hasChanges || saving"
            @click="saveSection"
          >
            {{ saving ? '保存中...' : '保存修改' }}
          </button>
          <button
            class="btn-reset"
            :disabled="!hasChanges"
            @click="resetSection"
          >
            重置
          </button>
          <span v-if="saveMsg" class="save-msg" :class="saveOk ? 'ok' : 'err'">{{ saveMsg }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { api } from "../api";

interface FieldSchema {
  key: string;
  label: string;
  type: string;
  description?: string;
  min?: number;
  max?: number;
  default?: any;
  options?: any[];
}

interface SectionSchema {
  key: string;
  label: string;
  description: string;
  fields: FieldSchema[];
}

const schema = ref<SectionSchema[]>([]);
const config = reactive<Record<string, any>>({});
const originalConfig = ref<string>(""); // JSON snapshot for change detection
const activeSection = ref("");
const loading = ref(true);
const saving = ref(false);
const saveMsg = ref("");
const saveOk = ref(false);

const currentSection = computed(() =>
  schema.value.find(s => s.key === activeSection.value) || null
);

const hasChanges = computed(() =>
  JSON.stringify(config) !== originalConfig.value
);

function getFieldValue(fieldKey: string): any {
  if (!activeSection.value) return undefined;
  const sectionData = config[activeSection.value];
  if (!sectionData) return undefined;

  // Support dotted keys (e.g., "max_single_position.max_pct")
  const parts = fieldKey.split(".");
  let val: any = sectionData;
  for (const p of parts) {
    if (val && typeof val === "object") {
      val = val[p];
    } else {
      return undefined;
    }
  }
  return val;
}

function setFieldValue(fieldKey: string, value: any) {
  if (!activeSection.value) return;
  if (!config[activeSection.value]) {
    config[activeSection.value] = {};
  }

  const parts = fieldKey.split(".");
  let obj: any = config[activeSection.value];
  for (let i = 0; i < parts.length - 1; i++) {
    if (!obj[parts[i]]) obj[parts[i]] = {};
    obj = obj[parts[i]];
  }
  obj[parts[parts.length - 1]] = value;
}

function resetSection() {
  if (!activeSection.value) return;
  const original = JSON.parse(originalConfig.value);
  config[activeSection.value] = JSON.parse(JSON.stringify(original[activeSection.value] || {}));
}

async function saveSection() {
  if (!activeSection.value) return;
  saving.value = true;
  saveMsg.value = "";
  try {
    const sectionData = config[activeSection.value];
    await api.saveSettingsSection(activeSection.value, sectionData);
    originalConfig.value = JSON.stringify(JSON.parse(JSON.stringify(config)));
    saveMsg.value = "保存成功";
    saveOk.value = true;
  } catch (err: any) {
    saveMsg.value = err?.message || "保存失败";
    saveOk.value = false;
  } finally {
    saving.value = false;
    setTimeout(() => { saveMsg.value = ""; }, 3000);
  }
}

onMounted(async () => {
  try {
    const [schemaData, settingsData] = await Promise.all([
      api.settingsSchema(),
      api.settings(),
    ]);
    schema.value = schemaData.sections || [];
    // Populate config from current settings
    for (const section of schema.value) {
      const sectionKey = section.key.split(".")[0]; // top-level key
      config[sectionKey] = JSON.parse(JSON.stringify(settingsData[sectionKey] || {}));
    }
    originalConfig.value = JSON.stringify(JSON.parse(JSON.stringify(config)));
    activeSection.value = schema.value[0]?.key || "";
  } catch (err) {
    console.error("Failed to load config schema:", err);
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.config-center {
  display: flex;
  flex-direction: column;
  min-height: 500px;
}
.config-loading {
  padding: 40px;
  text-align: center;
  color: var(--text-tertiary);
}
.config-layout {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  gap: 16px;
  height: calc(100vh - 200px);
}
.config-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  border-right: 1px solid var(--border, #333);
  padding-right: 12px;
  overflow-y: auto;
}
.nav-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}
.nav-item:hover {
  background: var(--bg-hover, rgba(255,255,255,0.04));
}
.nav-item.active {
  background: var(--accent-bg, rgba(99,102,241,0.15));
  color: var(--accent);
  font-weight: 600;
}
.nav-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nav-count {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 8px;
  background: rgba(125, 211, 252, 0.1);
  color: var(--text-tertiary);
}
.config-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: hidden;
  min-width: 0;
  width: 100%;
}
.editor-header h3 {
  font-size: 16px;
  margin: 0;
  color: var(--text-primary);
}
.editor-header p {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 4px 0 0;
}
.field-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  overflow-y: auto;
  padding-bottom: 8px;
  width: 100%;
}
.field-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.08);
  width: 100%;
  box-sizing: border-box;
}
.field-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
.field-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
}
.field-type {
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
  letter-spacing: 0.03em;
}
.type-int {
  background: rgba(99, 102, 241, 0.12);
  color: #818cf8;
}
.type-float {
  background: rgba(34, 197, 94, 0.12);
  color: #4ade80;
}
.type-string {
  background: rgba(251, 191, 36, 0.12);
  color: #fbbf24;
}
.field-input-wrap {
  flex-shrink: 0;
}
.field-input {
  width: 140px;
  padding: 5px 10px;
  border: 1px solid var(--border, #444);
  border-radius: 5px;
  background: rgba(0, 0, 0, 0.2);
  color: var(--text-primary);
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  outline: none;
  transition: border-color 0.15s;
  text-align: right;
}
.field-input:focus {
  border-color: var(--accent, #6366f1);
}
.field-range {
  font-size: 10px;
  color: var(--text-disabled);
  font-family: "JetBrains Mono", monospace;
  white-space: nowrap;
}
.field-default {
  font-size: 10px;
  color: var(--text-disabled);
  white-space: nowrap;
}
.editor-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 0;
  border-top: 1px solid var(--border-subtle);
  background: var(--bg-page, #0a0f1a);
}
.btn-save {
  padding: 8px 20px;
  border: none;
  border-radius: 6px;
  background: var(--accent, #6366f1);
  color: white;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.15s;
}
.btn-save:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn-reset {
  padding: 8px 16px;
  border: 1px solid var(--border, #444);
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}
.btn-reset:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.save-msg {
  font-size: 12px;
  font-weight: 500;
}
.save-msg.ok {
  color: var(--positive);
}
.save-msg.err {
  color: var(--negative);
}

@media (max-width: 760px) {
  .config-layout {
    grid-template-columns: 1fr;
  }
  .config-nav {
    flex-direction: row;
    overflow-x: auto;
    border-right: none;
    border-bottom: 1px solid var(--border, #333);
    padding-right: 0;
    padding-bottom: 8px;
  }
}
</style>
