import { computed, onMounted, reactive, ref, watch } from "vue";
import { api } from "../api";
import { useI18n } from "../i18n";

export function useConfigCenter() {

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
  const { t } = useI18n();
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

  function clone<T>(value: T): T {
    return JSON.parse(JSON.stringify(value ?? {}));
  }

  function getNestedValue(source: any, dottedKey: string): any {
    let current = source;
    for (const part of dottedKey.split(".")) {
      if (!current || typeof current !== "object") {
        return undefined;
      }
      current = current[part];
    }
    return current;
  }

  function setNestedValue(target: any, dottedKey: string, value: any) {
    const parts = dottedKey.split(".");
    let current = target;
    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i];
      if (!current[part] || typeof current[part] !== "object") {
        current[part] = {};
      }
      current = current[part];
    }
    current[parts[parts.length - 1]] = value;
  }

  function getSectionData(): any {
    if (!activeSection.value) return undefined;
    return getNestedValue(config, activeSection.value);
  }

  function getFieldValue(fieldKey: string): any {
    const sectionData = getSectionData();
    if (!sectionData) return undefined;
    return getNestedValue(sectionData, fieldKey);
  }

  function setFieldValue(fieldKey: string, value: any) {
    if (!activeSection.value) return;
    const sectionData = getSectionData() ?? {};
    setNestedValue(config, activeSection.value, sectionData);
    setNestedValue(sectionData, fieldKey, value);
  }

  function onSliderInput(field: FieldSchema, event: Event) {
    const raw = parseFloat((event.target as HTMLInputElement).value);
    const value = field.type === "int" ? Math.round(raw) : parseFloat(raw.toFixed(6));
    setFieldValue(field.key, value);
  }

  function resetSection() {
    if (!activeSection.value) return;
    const original = JSON.parse(originalConfig.value);
    setNestedValue(config, activeSection.value, clone(getNestedValue(original, activeSection.value) || {}));
  }

  async function saveSection() {
    if (!activeSection.value) return;
    saving.value = true;
    saveMsg.value = "";
    try {
      const sectionData = clone(getSectionData() || {});
      await api.saveSettingsSection(activeSection.value, sectionData);
      originalConfig.value = JSON.stringify(clone(config));
      saveMsg.value = t("configCenter.saveSuccess");
      saveOk.value = true;
    } catch (err: any) {
      saveMsg.value = err?.message || t("configCenter.saveError");
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
      Object.assign(config, clone(settingsData));
      originalConfig.value = JSON.stringify(clone(config));
      activeSection.value = schema.value[0]?.key || "";
    } catch (err) {
      console.error("Failed to load config schema:", err);
    } finally {
      loading.value = false;
    }
  });

  return {
    schema,
    t,
    config,
    originalConfig,
    activeSection,
    loading,
    saving,
    saveMsg,
    saveOk,
    currentSection,
    hasChanges,
    getNestedValue,
    setNestedValue,
    getSectionData,
    getFieldValue,
    setFieldValue,
    onSliderInput,
    resetSection,
    saveSection,
  };
}
