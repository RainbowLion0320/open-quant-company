<template>
  <div class="ast-intelligence view-page">
    <div class="ast-toolbar glass-card">
      <div>
        <h2>{{ t("astIntelligence.title") }}</h2>
        <p>{{ t("astIntelligence.subtitle") }}</p>
      </div>
      <button class="icon-button" @click="load" :aria-label="t('astIntelligence.refresh')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/></svg>
      </button>
    </div>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="load">{{ t("common.retry") }}</button>
    </div>

    <section v-if="payload?.status === 'no_artifact'" class="ast-command glass-card">
      <span>{{ t("astIntelligence.noArtifact") }}</span>
      <code>{{ payload.recommended_command }}</code>
    </section>

    <section class="ast-metrics">
      <article class="ast-metric glass-card score">
        <small>{{ t("astIntelligence.duplicateScore") }}</small>
        <strong>{{ payload?.summary.duplicate_score ?? 0 }}</strong>
        <em>{{ generatedAt }}</em>
      </article>
      <article class="ast-metric glass-card">
        <small>{{ t("astIntelligence.issues") }}</small>
        <strong>{{ filteredIssues.length }}</strong>
        <em>{{ severityText }}</em>
      </article>
      <article class="ast-metric glass-card">
        <small>{{ t("astIntelligence.cloneGroups") }}</small>
        <strong>{{ filteredGroups.length }}</strong>
        <em>{{ t("astIntelligence.totalGroups", { count: payload?.summary.clone_group_count ?? 0 }) }}</em>
      </article>
      <article class="ast-metric glass-card">
        <small>{{ t("astIntelligence.units") }}</small>
        <strong>{{ payload?.summary.unit_count ?? 0 }}</strong>
        <em>{{ t("astIntelligence.files", { count: payload?.summary.file_count ?? 0 }) }}</em>
      </article>
      <article class="ast-metric glass-card">
        <small>{{ t("astIntelligence.languages") }}</small>
        <strong>{{ languageEntries.length }}</strong>
        <em>{{ languageEntries.map(([key, count]) => `${key}:${count}`).join(" · ") || "—" }}</em>
      </article>
    </section>

    <section class="ast-filters glass-card">
      <label>
        <span>{{ t("astIntelligence.severity") }}</span>
        <select v-model="severityFilter">
          <option value="all">{{ t("astIntelligence.all") }}</option>
          <option value="P0">P0</option>
          <option value="P1">P1</option>
          <option value="P2">P2</option>
        </select>
      </label>
      <label>
        <span>{{ t("astIntelligence.category") }}</span>
        <select v-model="categoryFilter">
          <option value="all">{{ t("astIntelligence.all") }}</option>
          <option v-for="category in categories" :key="category" :value="category">{{ category }}</option>
        </select>
      </label>
      <label>
        <span>{{ t("astIntelligence.language") }}</span>
        <select v-model="languageFilter">
          <option value="all">{{ t("astIntelligence.all") }}</option>
          <option v-for="[language] in languageEntries" :key="language" :value="language">{{ language }}</option>
        </select>
      </label>
      <label>
        <span>{{ t("astIntelligence.module") }}</span>
        <select v-model="moduleFilter">
          <option value="all">{{ t("astIntelligence.all") }}</option>
          <option v-for="module in modules" :key="module" :value="module">{{ module }}</option>
        </select>
      </label>
    </section>

    <section class="ast-grid">
      <article class="glass-card ast-panel">
        <div class="panel-head">
          <span>{{ t("astIntelligence.heatmap") }}</span>
          <small>{{ t("astIntelligence.heatmapMeta") }}</small>
        </div>
        <div class="heatmap">
          <button
            v-for="cell in heatmapCells"
            :key="`${cell.module}:${cell.language}`"
            class="heatmap-cell"
            :class="{ active: moduleFilter === cell.module || languageFilter === cell.language }"
            :style="heatStyle(cell.count)"
            @click="selectCell(cell.module, cell.language)"
          >
            <strong>{{ cell.module }}</strong>
            <span>{{ cell.language }}</span>
            <em>{{ cell.count }}</em>
          </button>
          <p v-if="!heatmapCells.length" class="empty-text">{{ t("astIntelligence.noHeatmap") }}</p>
        </div>
      </article>

      <article class="glass-card ast-panel">
        <div class="panel-head">
          <span>{{ t("astIntelligence.cloneGroups") }}</span>
          <small>{{ filteredGroups.length }}</small>
        </div>
        <div class="group-list">
          <button
            v-for="group in filteredGroups"
            :key="group.id"
            class="group-item"
            :class="{ active: selectedGroupId === group.id }"
            @click="selectedGroupId = group.id"
          >
            <strong>{{ group.category }} · {{ Math.round(group.similarity * 100) }}%</strong>
            <span>{{ group.units.map(unit => `${unit.path}:${unit.start_line}`).join("  ") }}</span>
            <em>{{ group.shared_shape }}</em>
          </button>
          <p v-if="!filteredGroups.length" class="empty-text">{{ t("astIntelligence.noGroups") }}</p>
        </div>
      </article>
    </section>

    <section class="ast-detail-grid">
      <article class="glass-card ast-panel inspector">
        <div class="panel-head">
          <span>{{ t("astIntelligence.inspector") }}</span>
          <small>{{ selectedGroup?.id || "—" }}</small>
        </div>
        <template v-if="selectedGroup">
          <div class="group-summary">
            <strong>{{ selectedGroup.category }}</strong>
            <span>{{ t("astIntelligence.similarity", { value: Math.round(selectedGroup.similarity * 100) }) }}</span>
          </div>
          <div class="unit-list">
            <div v-for="unit in selectedGroup.units" :key="unit.id" class="unit-row">
              <strong>{{ unit.name }}</strong>
              <code>{{ unit.path }}:{{ unit.start_line }}-{{ unit.end_line }}</code>
              <span>{{ unit.language }} · {{ unit.kind }} · {{ unit.node_count }}</span>
            </div>
          </div>
          <div class="module-pairs" v-if="selectedGroup.module_pairs.length">
            <code v-for="pair in selectedGroup.module_pairs" :key="pair">{{ pair }}</code>
          </div>
        </template>
        <p v-else class="empty-text">{{ t("astIntelligence.noSelectedGroup") }}</p>
      </article>

      <article class="glass-card ast-panel issue-panel">
        <div class="panel-head">
          <span>{{ t("astIntelligence.diagnostics") }}</span>
          <small>{{ filteredIssues.length }}</small>
        </div>
        <div class="issue-list">
          <button
            v-for="issue in filteredIssues"
            :key="issue.id"
            class="issue-item"
            :class="issue.severity.toLowerCase()"
            @click="selectIssue(issue.id)"
          >
            <strong>{{ issue.severity }} · {{ issue.title }}</strong>
            <span>{{ issue.paths.join("  ") }}</span>
            <em>{{ issue.recommendation }}</em>
          </button>
          <p v-if="!filteredIssues.length" class="empty-text">{{ t("astIntelligence.noIssues") }}</p>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import type { AstCloneGroup, AstIntelligenceResponse, AstIssue } from "../api";
import { useI18n } from "../i18n";

const { currentLocale, t } = useI18n();
const payload = ref<AstIntelligenceResponse | null>(null);
const error = ref("");
const severityFilter = ref("all");
const categoryFilter = ref("all");
const languageFilter = ref("all");
const moduleFilter = ref("all");
const selectedGroupId = ref("");

const languageEntries = computed(() => Object.entries(payload.value?.summary.languages || {}).sort((a, b) => b[1] - a[1]));
const categories = computed(() => Array.from(new Set((payload.value?.issues || []).map(item => item.category))).sort());
const modules = computed(() => Array.from(new Set((payload.value?.clone_groups || []).flatMap(group => group.units.map(unit => topModule(unit.path))))).sort());
const filteredIssues = computed(() => (payload.value?.issues || []).filter(matchesIssue).slice(0, 120));
const filteredGroups = computed(() => (payload.value?.clone_groups || []).filter(matchesGroup).slice(0, 120));
const selectedGroup = computed(() => filteredGroups.value.find(item => item.id === selectedGroupId.value) || filteredGroups.value[0] || null);
const generatedAt = computed(() => fmtDate(payload.value?.generated_at || payload.value?.latest?.generated_at || ""));
const severityText = computed(() => {
  const counts = payload.value?.summary.severity_counts || {};
  return ["P0", "P1", "P2"].map(key => `${key}:${counts[key] || 0}`).join(" · ");
});
const heatmapCells = computed(() => {
  const counts = new Map<string, { module: string; language: string; count: number }>();
  for (const group of payload.value?.clone_groups || []) {
    for (const unit of group.units) {
      const module = topModule(unit.path);
      const key = `${module}:${unit.language}`;
      const cell = counts.get(key) || { module, language: unit.language, count: 0 };
      cell.count += 1;
      counts.set(key, cell);
    }
  }
  return Array.from(counts.values()).sort((a, b) => b.count - a.count).slice(0, 80);
});
const maxHeat = computed(() => Math.max(1, ...heatmapCells.value.map(item => item.count)));

async function load() {
  error.value = "";
  try {
    const next = await api.astIntelligence();
    payload.value = next;
    selectedGroupId.value = next.clone_groups[0]?.id || "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : t("astIntelligence.loadError");
  }
}

function matchesIssue(issue: AstIssue) {
  if (severityFilter.value !== "all" && issue.severity !== severityFilter.value) return false;
  if (categoryFilter.value !== "all" && issue.category !== categoryFilter.value) return false;
  if (languageFilter.value !== "all" && issue.language !== languageFilter.value) return false;
  if (moduleFilter.value !== "all" && !issue.paths.some(path => topModule(path) === moduleFilter.value)) return false;
  return true;
}

function matchesGroup(group: AstCloneGroup) {
  if (categoryFilter.value !== "all" && group.category !== categoryFilter.value) return false;
  if (languageFilter.value !== "all" && !group.units.some(unit => unit.language === languageFilter.value)) return false;
  if (moduleFilter.value !== "all" && !group.units.some(unit => topModule(unit.path) === moduleFilter.value)) return false;
  if (severityFilter.value !== "all") {
    const matching = (payload.value?.issues || []).some(issue => issue.severity === severityFilter.value && issue.id.includes(group.id));
    if (!matching) return false;
  }
  return true;
}

function selectCell(module: string, language: string) {
  moduleFilter.value = moduleFilter.value === module ? "all" : module;
  languageFilter.value = languageFilter.value === language ? "all" : language;
}

function selectIssue(issueId: string) {
  const group = (payload.value?.clone_groups || []).find(item => issueId.includes(item.id));
  if (group) selectedGroupId.value = group.id;
}

function heatStyle(value: number) {
  const intensity = value / maxHeat.value;
  return {
    backgroundColor: `rgba(34, 197, 94, ${0.08 + intensity * 0.34})`,
    borderColor: `rgba(34, 197, 94, ${0.18 + intensity * 0.54})`,
  };
}

function topModule(path: string) {
  return path.split("/", 1)[0] || path;
}

function fmtDate(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(currentLocale.value);
}

onMounted(load);
</script>

<style scoped src="../styles/views/ast-intelligence.css"></style>
