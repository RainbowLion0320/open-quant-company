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

    <section class="ast-overview">
      <article class="ast-overview-card ast-status-strip glass-card">
        <div class="risk-summary-main">
          <small>{{ t("astIntelligence.totalRisks") }}</small>
          <strong>{{ issueTotal }}</strong>
        </div>

        <div class="severity-chips">
          <span v-for="entry in severityEntries" :key="entry.key" class="severity-chip" :class="entry.key.toLowerCase()">
            <b>{{ entry.key }}</b>
            <span>{{ entry.count }}</span>
          </span>
        </div>

        <div class="coverage-grid" :aria-label="t('astIntelligence.scanCoverage')">
          <span><b>{{ payload?.summary.file_count ?? 0 }}</b>{{ t("astIntelligence.filesShort") }}</span>
          <span><b>{{ payload?.summary.unit_count ?? 0 }}</b>{{ t("astIntelligence.unitsShort") }}</span>
          <span><b>{{ languageEntries.length }}</b>{{ t("astIntelligence.languagesShort") }}</span>
        </div>

        <em>{{ latestScanMeta }}</em>

        <button class="artifact-refresh" @click="load" :aria-label="t('astIntelligence.refresh')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/></svg>
        </button>
      </article>
    </section>

    <section class="ast-risk-layout">
      <article class="glass-card ast-panel risk-list-panel">
        <div class="panel-head">
          <span>{{ t("astIntelligence.riskList") }}</span>
          <small class="ast-list-meta">
            <span>{{ latestScanMeta }}</span>
            <span aria-hidden="true">·</span>
            <span>{{ t("astIntelligence.visibleIssues", { count: visibleIssues.length, total: issueTotal }) }}</span>
          </small>
        </div>
        <div class="risk-list">
          <button
            v-for="issue in visibleIssues"
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
          <p v-if="!visibleIssues.length" class="empty-text">{{ t("astIntelligence.noIssues") }}</p>
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
import type { AstIntelligenceResponse } from "../api";
import { useI18n } from "../i18n";

const { t } = useI18n();
const payload = ref<AstIntelligenceResponse | null>(null);
const error = ref("");
const selectedIssueId = ref("");

const languageEntries = computed(() => Object.entries(payload.value?.summary.languages || {}).sort((a, b) => b[1] - a[1]));
const visibleIssues = computed(() => (payload.value?.issues || []).slice(0, 120));
const selectedIssue = computed(() => visibleIssues.value.find(item => item.id === selectedIssueId.value) || visibleIssues.value[0] || null);
const issueClone = computed(() => {
  const issue = selectedIssue.value;
  if (!issue) return null;
  const evidenceGroup = typeof issue.evidence?.clone_group_id === "string" ? issue.evidence.clone_group_id : "";
  return (payload.value?.clone_groups || []).find(item => item.id === evidenceGroup || issue.id.includes(item.id)) || null;
});
const issueTotal = computed(() => payload.value?.summary.issue_count ?? payload.value?.issues.length ?? 0);
const severityEntries = computed(() => {
  const counts = payload.value?.summary.severity_counts || {};
  return ["P0", "P1", "P2"].map(key => ({ key, count: counts[key] || 0 }));
});
const latestScanMeta = computed(() => {
  const generatedAt = payload.value?.latest?.generated_at || payload.value?.generated_at || "";
  if (!generatedAt) return t("astIntelligence.scanTimeUnknown");
  const time = formatScanTime(generatedAt);
  return t("astIntelligence.latestScan", { time });
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

function formatScanTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return t("astIntelligence.scanTimeUnknown");
  const now = new Date();
  const sameYear = date.getFullYear() === now.getFullYear();
  const datePart = sameYear
    ? t("astIntelligence.scanDateShort", { month: date.getMonth() + 1, day: date.getDate() })
    : t("astIntelligence.scanDateLong", { year: date.getFullYear(), month: date.getMonth() + 1, day: date.getDate() });
  return `${datePart} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
}

function pad2(value: number) {
  return String(value).padStart(2, "0");
}

onMounted(load);
</script>

<style scoped src="../styles/views/ast-intelligence.css"></style>
