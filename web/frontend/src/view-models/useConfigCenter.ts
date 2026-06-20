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
  const activeGroup = ref("");
  const loading = ref(true);
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
    if (section.key.startsWith("strategies.") && !section.key.endsWith(".params")) return 0;
    if (section.key.startsWith("strategies.") && section.key.endsWith(".params")) return 1;
    if (section.key.startsWith("signal_selection.strategies.")) return 2;
    return 3;
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

  function clone<T>(value: T): T {
    return JSON.parse(JSON.stringify(value ?? {}));
  }

  function getNestedValue(source: any, dottedKey: string): any {
    let current = source;
    for (const part of dottedKey.split(".")) {
      if (!isSafePathPart(part)) return undefined;
      if (!current || typeof current !== "object") {
        return undefined;
      }
      current = current[part];
    }
    return current;
  }

  function isSafePathPart(part: string): boolean {
    return Boolean(part) && part !== "__proto__" && part !== "prototype" && part !== "constructor";
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

  function optionLabel(field: FieldSchema, value: any): string {
    const match = (field.options || []).find(option => String(option?.value ?? option) === String(value));
    if (!match) return String(value);
    return String(match.label ?? match.value ?? match);
  }

  function formatValue(value: any): string {
    if (value === undefined || value === null || value === "") return "—";
    if (Array.isArray(value)) return value.length ? value.join(", ") : "[]";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function displayFieldValue(sectionKey: string, field: FieldSchema): string {
    const value = getFieldValue(sectionKey, field.key);
    if (field.type === "bool") {
      return value ? t("common.enabled") : t("common.disabled");
    }
    if (field.type === "select" && value !== undefined && value !== null && value !== "") {
      return optionLabel(field, value);
    }
    return formatValue(value);
  }

  function fieldValueClass(sectionKey: string, field: FieldSchema): string {
    if (field.type !== "bool") return "";
    return getFieldValue(sectionKey, field.key) ? "is-enabled" : "is-disabled";
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
    activeGroup,
    loading,
    editorScrollRef,
    activeSubgroupKey,
    activeGroupInfo,
    activeSections,
    groupedSections,
    strategyNavItems,
    visibleSubgroupKey,
    setActiveGroup,
    jumpToSubgroup,
    subgroupDomId,
    navItemMeta,
    strategyStatusLabel,
    navButtonTitle,
    subgroupMeta,
    getNestedValue,
    getSectionData,
    getFieldValue,
    displayFieldValue,
    fieldValueClass,
  };
}
