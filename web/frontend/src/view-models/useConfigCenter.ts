import { computed, onMounted, reactive, ref } from "vue";
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
    group: string;
    subgroup?: string;
    subgroup_label?: string;
    order?: number;
    fields: FieldSchema[];
  }

  interface GroupSchema {
    key: string;
    label: string;
    description: string;
    section_count: number;
    field_count: number;
  }

  const schema = ref<SectionSchema[]>([]);
  const groups = ref<GroupSchema[]>([]);
  const { t } = useI18n();
  const config = reactive<Record<string, any>>({});
  const originalConfig = ref<string>(""); // JSON snapshot for change detection
  const activeGroup = ref("");
  const loading = ref(true);
  const savingSection = ref("");
  const saveMsgSection = ref("");
  const saveMsg = ref("");
  const saveOk = ref(false);

  const activeGroupInfo = computed(() =>
    groups.value.find(group => group.key === activeGroup.value) || null
  );

  const activeSections = computed(() =>
    schema.value.filter(section => section.group === activeGroup.value)
  );

  const groupedSections = computed(() => {
    const map: Record<string, { key: string; label: string; sections: SectionSchema[] }> = {};
    for (const section of activeSections.value) {
      const key = section.subgroup || section.key;
      if (!map[key]) {
        map[key] = { key, label: section.subgroup_label || section.label, sections: [] };
      }
      map[key].sections.push(section);
    }
    return Object.values(map).map(group => ({
      ...group,
      sections: group.sections.slice().sort((a, b) => (a.order ?? 0) - (b.order ?? 0)),
    }));
  });

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

  function getSectionData(sectionKey: string): any {
    if (!sectionKey) return undefined;
    return getNestedValue(config, sectionKey);
  }

  function getFieldValue(sectionKey: string, fieldKey: string): any {
    const sectionData = getSectionData(sectionKey);
    if (!sectionData) return undefined;
    return getNestedValue(sectionData, fieldKey);
  }

  function setFieldValue(sectionKey: string, fieldKey: string, value: any) {
    if (!sectionKey) return;
    const sectionData = getSectionData(sectionKey) ?? {};
    setNestedValue(config, sectionKey, sectionData);
    setNestedValue(sectionData, fieldKey, value);
  }

  function onSliderInput(sectionKey: string, field: FieldSchema, event: Event) {
    const raw = parseFloat((event.target as HTMLInputElement).value);
    const value = field.type === "int" ? Math.round(raw) : parseFloat(raw.toFixed(6));
    setFieldValue(sectionKey, field.key, value);
  }

  function coerceNumericField(field: FieldSchema, event: Event) {
    const raw = (event.target as HTMLInputElement).value;
    if (raw === "") return undefined;
    return field.type === "int" ? parseInt(raw) : parseFloat(raw);
  }

  function sectionHasChanges(sectionKey: string) {
    if (!originalConfig.value || !sectionKey) return false;
    const original = JSON.parse(originalConfig.value);
    return JSON.stringify(getNestedValue(config, sectionKey) ?? {}) !==
      JSON.stringify(getNestedValue(original, sectionKey) ?? {});
  }

  function resetSection(sectionKey: string) {
    if (!sectionKey) return;
    const original = JSON.parse(originalConfig.value);
    setNestedValue(config, sectionKey, clone(getNestedValue(original, sectionKey) || {}));
  }

  async function saveSection(sectionKey: string) {
    if (!sectionKey) return;
    savingSection.value = sectionKey;
    saveMsgSection.value = sectionKey;
    saveMsg.value = "";
    try {
      const sectionData = clone(getSectionData(sectionKey) || {});
      await api.saveSettingsSection(sectionKey, sectionData);
      originalConfig.value = JSON.stringify(clone(config));
      saveMsg.value = t("configCenter.saveSuccess");
      saveOk.value = true;
    } catch (err: any) {
      saveMsg.value = err?.message || t("configCenter.saveError");
      saveOk.value = false;
    } finally {
      savingSection.value = "";
      setTimeout(() => { saveMsg.value = ""; }, 3000);
    }
  }

  function isSaving(sectionKey: string) {
    return savingSection.value === sectionKey;
  }

  onMounted(async () => {
    try {
      const [schemaData, settingsData] = await Promise.all([
        api.settingsSchema(),
        api.settings(),
      ]);
      schema.value = schemaData.sections || [];
      groups.value = schemaData.groups || [];
      Object.assign(config, clone(settingsData));
      originalConfig.value = JSON.stringify(clone(config));
      activeGroup.value = groups.value[0]?.key || schema.value[0]?.group || "";
    } catch (err) {
      console.error("Failed to load config schema:", err);
    } finally {
      loading.value = false;
    }
  });

  return {
    schema,
    groups,
    t,
    config,
    originalConfig,
    activeGroup,
    loading,
    savingSection,
    saveMsgSection,
    saveMsg,
    saveOk,
    activeGroupInfo,
    activeSections,
    groupedSections,
    hasChanges,
    getNestedValue,
    setNestedValue,
    getSectionData,
    getFieldValue,
    setFieldValue,
    onSliderInput,
    coerceNumericField,
    sectionHasChanges,
    resetSection,
    saveSection,
    isSaving,
  };
}
