import { computed, nextTick, onMounted, reactive, ref } from "vue";
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
    strategy_name?: string;
    strategy_label?: string;
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

  interface StrategyNavItem {
    key: string;
    label: string;
    sectionCount: number;
    fieldCount: number;
    enabled: boolean | null;
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
  const editorScrollRef = ref<HTMLElement | null>(null);
  const activeSubgroupKey = ref("");

  const activeGroupInfo = computed(() =>
    groups.value.find(group => group.key === activeGroup.value) || null
  );

  const activeSections = computed(() =>
    schema.value.filter(section => section.group === activeGroup.value)
  );

  function sectionStrategyName(section: SectionSchema): string {
    if (section.strategy_name) return section.strategy_name;
    if (section.key.startsWith("strategies.")) return section.key.split(".")[1] || "";
    if (section.key.startsWith("signal_selection.strategies.")) return section.key.split(".")[2] || "";
    if (section.key === "ml" || section.key.startsWith("ml.")) return "ml_lgbm";
    if (section.key.startsWith("buffett.")) return "buffett";
    if (section.key.startsWith("signals.multifactor")) return "multifactor";
    return "";
  }

  function strategySectionRank(section: SectionSchema): number {
    if (section.key.startsWith("strategies.")) return 0;
    if (section.key.startsWith("signal_selection.strategies.")) return 1;
    return 2;
  }

  const groupedSections = computed(() => {
    const strategyLabels: Record<string, string> = {};
    if (activeGroup.value === "strategy_management") {
      for (const section of activeSections.value) {
        const name = sectionStrategyName(section);
        if (name && section.strategy_label) strategyLabels[name] = section.strategy_label;
      }
    }

    const map: Record<string, { key: string; label: string; sections: SectionSchema[]; order: number; strategyName?: string }> = {};
    for (const section of activeSections.value) {
      const strategyName = activeGroup.value === "strategy_management" ? sectionStrategyName(section) : "";
      const key = strategyName ? `strategy:${strategyName}` : (section.subgroup || section.key);
      if (!map[key]) {
        const label = strategyName
          ? (strategyLabels[strategyName] || section.strategy_label || section.subgroup_label || strategyName)
          : (section.subgroup_label || section.label);
        map[key] = { key, label, sections: [], order: section.order ?? 0, strategyName: strategyName || undefined };
      }
      map[key].sections.push(section);
      map[key].order = Math.min(map[key].order, section.order ?? map[key].order);
    }
    return Object.values(map)
      .map(group => ({
        ...group,
        sections: group.sections.slice().sort((a, b) =>
          strategySectionRank(a) - strategySectionRank(b) || (a.order ?? 0) - (b.order ?? 0)
        ),
      }))
      .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label));
  });

  const strategyNavItems = computed(() => {
    if (activeGroup.value !== "strategy_management") return [];
    return groupedSections.value.map(group => ({
      key: group.key,
      label: group.label,
      sectionCount: group.sections.length,
      fieldCount: group.sections.reduce((sum, section) => sum + section.fields.length, 0),
      enabled: group.strategyName ? getNestedValue(config, `strategies.${group.strategyName}.enabled`) !== false : null,
    }));
  });

  const visibleSubgroupKey = computed(() =>
    activeSubgroupKey.value || strategyNavItems.value[0]?.key || groupedSections.value[0]?.key || ""
  );

  function subgroupDomId(key: string): string {
    return `config-subgroup-${key.replace(/[^A-Za-z0-9_-]/g, "-")}`;
  }

  function setActiveGroup(groupKey: string) {
    activeGroup.value = groupKey;
    activeSubgroupKey.value = "";
    nextTick(() => {
      if (editorScrollRef.value) editorScrollRef.value.scrollTop = 0;
    });
  }

  async function jumpToSubgroup(groupKey: string) {
    activeSubgroupKey.value = groupKey;
    await nextTick();
    const container = editorScrollRef.value;
    const target = document.getElementById(subgroupDomId(groupKey));
    if (!container || !target) return;
    const top = container.scrollTop + target.getBoundingClientRect().top - container.getBoundingClientRect().top;
    container.scrollTo({ top: Math.max(0, top - 2), behavior: "smooth" });
  }

  function navItemLabel(item: StrategyNavItem): string {
    return `${item.label} · ${item.sectionCount} / ${item.fieldCount}`;
  }

  function navItemMeta(item: StrategyNavItem): string {
    return t("configCenter.strategyNavMeta", { sections: item.sectionCount, fields: item.fieldCount });
  }

  function strategyStatusLabel(item: StrategyNavItem): string {
    if (item.enabled === null) return "";
    return t(item.enabled ? "configCenter.strategyEnabled" : "configCenter.strategyDisabled");
  }

  function navButtonTitle(item: StrategyNavItem): string {
    const status = strategyStatusLabel(item);
    const label = status ? `${navItemLabel(item)} · ${status}` : navItemLabel(item);
    return t("configCenter.strategyJumpTo", { label });
  }

  function subgroupMeta(sections: SectionSchema[]): string {
    const fields = sections.reduce((sum, section) => sum + section.fields.length, 0);
    return t("configCenter.subgroupFieldSummary", { sections: sections.length, fields });
  }

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
      setActiveGroup(groups.value[0]?.key || schema.value[0]?.group || "");
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
    editorScrollRef,
    activeSubgroupKey,
    activeGroupInfo,
    activeSections,
    groupedSections,
    strategyNavItems,
    visibleSubgroupKey,
    hasChanges,
    setActiveGroup,
    jumpToSubgroup,
    subgroupDomId,
    navItemMeta,
    strategyStatusLabel,
    navButtonTitle,
    subgroupMeta,
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
