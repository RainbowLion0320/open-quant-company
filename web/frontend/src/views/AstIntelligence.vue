<template>
  <div class="ast-intelligence view-page">
    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="load">{{ t("common.retry") }}</button>
    </div>

    <section v-if="payload?.status === 'no_artifact'" class="ast-command glass-card">
      <span>{{ t("astIntelligence.noArtifact") }}</span>
      <code>{{ payload.recommended_command }}</code>
    </section>

    <section class="ast-metrics">
      <article class="ast-metric glass-card risk metric-with-action">
        <button class="artifact-refresh" @click="load" :aria-label="t('astIntelligence.refresh')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/></svg>
        </button>
        <small>{{ t("astIntelligence.duplicateRisks") }}</small>
        <strong>{{ payload?.summary.issue_count ?? payload?.issues.length ?? 0 }}</strong>
        <em>{{ severityText }}</em>
      </article>
      <article class="ast-metric glass-card">
        <small>{{ t("astIntelligence.similarityGroups") }}</small>
        <strong>{{ payload?.summary.clone_group_count ?? 0 }}</strong>
        <em>{{ t("astIntelligence.similarityContext") }}</em>
      </article>
      <article class="ast-metric glass-card">
        <small>{{ t("astIntelligence.productionRisks") }}</small>
        <strong>{{ productionIssueCount }}</strong>
        <em>{{ t("astIntelligence.nonProductionRisks", { count: nonProductionIssueCount }) }}</em>
      </article>
      <article class="ast-metric glass-card">
        <small>{{ t("astIntelligence.canonicalBypass") }}</small>
        <strong>{{ canonicalBypassCount }}</strong>
        <em>{{ t("astIntelligence.categoryRisk") }}</em>
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

    <section class="ast-risk-layout">
      <article class="glass-card ast-panel risk-list-panel">
        <div class="panel-head">
          <span>{{ t("astIntelligence.riskList") }}</span>
          <small>{{ t("astIntelligence.filteredIssues", { count: filteredIssues.length, total: issueTotal }) }}</small>
        </div>
        <div class="risk-list">
          <button
            v-for="issue in filteredIssues"
            :key="issue.id"
            class="risk-item"
            :class="[issue.severity.toLowerCase(), { active: selectedIssue?.id === issue.id }]"
            @click="selectedIssueId = issue.id"
          >
            <div class="risk-item-head">
              <strong>{{ issue.severity }} · {{ issue.title }}</strong>
              <span>{{ issue.category }}</span>
            </div>
            <p>{{ issue.paths.join("  ") }}</p>
            <em>{{ issue.recommendation }}</em>
          </button>
          <p v-if="!filteredIssues.length" class="empty-text">{{ t("astIntelligence.noIssues") }}</p>
        </div>
      </article>

      <article class="glass-card ast-panel issue-detail-panel">
        <div class="panel-head">
          <span>{{ t("astIntelligence.issueDetail") }}</span>
          <small>{{ selectedIssue?.id || "—" }}</small>
        </div>
        <template v-if="selectedIssue">
          <div class="issue-detail-summary" :class="selectedIssue.severity.toLowerCase()">
            <strong>{{ selectedIssue.severity }} · {{ selectedIssue.title }}</strong>
            <span>{{ selectedIssue.category }} · {{ selectedIssue.language }}</span>
          </div>

          <section class="issue-detail-section">
            <h3>{{ t("astIntelligence.affectedFiles") }}</h3>
            <div class="path-list">
              <code v-for="path in selectedIssue.paths" :key="path">{{ path }}</code>
            </div>
          </section>

          <section v-if="selectedIssue.units.length" class="issue-detail-section">
            <h3>{{ t("astIntelligence.involvedUnits") }}</h3>
            <div class="unit-list">
              <div v-for="unit in selectedIssue.units" :key="unit.id" class="unit-row">
                <strong>{{ unit.name }}</strong>
                <code>{{ unit.path }}:{{ unit.start_line }}-{{ unit.end_line }}</code>
                <span>{{ unit.language }} · {{ unit.kind }} · {{ unit.node_count }}</span>
              </div>
            </div>
          </section>

          <section v-if="issueClone" class="issue-detail-section">
            <h3>{{ t("astIntelligence.similarityContext") }}</h3>
            <div class="clone-context">
              <strong>{{ issueClone.category }} · {{ t("astIntelligence.similarity", { value: Math.round(issueClone.similarity * 100) }) }}</strong>
              <span>{{ issueClone.shared_shape }}</span>
            </div>
            <div class="module-pairs" v-if="issueClone.module_pairs.length">
              <code v-for="pair in issueClone.module_pairs" :key="pair">{{ pair }}</code>
            </div>
          </section>

          <section class="issue-detail-section">
            <h3>{{ t("astIntelligence.recommendation") }}</h3>
            <p>{{ selectedIssue.recommendation }}</p>
          </section>

          <section v-if="Object.keys(selectedIssue.evidence || {}).length" class="issue-detail-section">
            <h3>{{ t("astIntelligence.evidence") }}</h3>
            <pre>{{ JSON.stringify(selectedIssue.evidence, null, 2) }}</pre>
          </section>
        </template>
        <p v-else class="empty-text">{{ t("astIntelligence.noSelectedIssue") }}</p>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import type { AstIntelligenceResponse, AstIssue } from "../api";
import { useI18n } from "../i18n";
import { topModule } from "../utils/intelligenceViews";

const { t } = useI18n();
const payload = ref<AstIntelligenceResponse | null>(null);
const error = ref("");
const severityFilter = ref("all");
const categoryFilter = ref("all");
const languageFilter = ref("all");
const moduleFilter = ref("all");
const selectedIssueId = ref("");

const languageEntries = computed(() => Object.entries(payload.value?.summary.languages || {}).sort((a, b) => b[1] - a[1]));
const categories = computed(() => Array.from(new Set((payload.value?.issues || []).map(item => item.category))).sort());
const modules = computed(() => Array.from(new Set((payload.value?.issues || []).flatMap(issue => issue.paths.map(path => topModule(path))))).sort());
const filteredIssues = computed(() => (payload.value?.issues || []).filter(matchesIssue).slice(0, 120));
const selectedIssue = computed(() => filteredIssues.value.find(item => item.id === selectedIssueId.value) || filteredIssues.value[0] || null);
const issueClone = computed(() => {
  const issue = selectedIssue.value;
  if (!issue) return null;
  const evidenceGroup = typeof issue.evidence?.clone_group_id === "string" ? issue.evidence.clone_group_id : "";
  return (payload.value?.clone_groups || []).find(item => item.id === evidenceGroup || issue.id.includes(item.id)) || null;
});
const issueTotal = computed(() => payload.value?.summary.issue_count ?? payload.value?.issues.length ?? 0);
const productionIssueCount = computed(() => (payload.value?.issues || []).filter(issue => issue.paths.some(isProductionPath)).length);
const nonProductionIssueCount = computed(() => Math.max(0, (payload.value?.summary.issue_count ?? payload.value?.issues.length ?? 0) - productionIssueCount.value));
const canonicalBypassCount = computed(() => (payload.value?.issues || []).filter(issue => issue.category === "canonical_bypass").length);
const severityText = computed(() => {
  const counts = payload.value?.summary.severity_counts || {};
  return ["P0", "P1", "P2"].map(key => `${key}:${counts[key] || 0}`).join(" · ");
});

async function load() {
  error.value = "";
  try {
    const next = await api.astIntelligence();
    payload.value = next;
    selectedIssueId.value = next.issues[0]?.id || "";
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

function isProductionPath(path: string) {
  const normalized = path.replace(/^\.\/+/, "");
  if (!normalized) return false;
  if (/^(tests|docs|wiki|reports|var|node_modules|web\/frontend\/dist)\//.test(normalized)) return false;
  if (/^(\.github|\.codegraph)\//.test(normalized)) return false;
  if (/^(README(\.en)?|AGENTS|CLAUDE|CONTRIBUTING|SECURITY|SUPPORT|CODE_OF_CONDUCT|CHANGELOG|LICENSE|NOTICE)(\.md)?$/.test(normalized)) return false;
  return true;
}

onMounted(load);
</script>

<style scoped src="../styles/views/ast-intelligence.css"></style>
