<template>
  <div class="test-design view-page">
    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="load">{{ t("common.retry") }}</button>
    </div>

    <section v-if="design?.status === 'no_artifact'" class="design-command glass-card">
      <span>{{ t("testDesign.noArtifact") }}</span>
      <code>{{ design.recommended_command }}</code>
    </section>

    <section class="design-metrics">
      <article class="design-metric design-risk-summary glass-card smell metric-with-action">
        <button class="artifact-refresh" @click="load" :aria-label="t('testDesign.refresh')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/></svg>
        </button>
        <small>{{ t("testDesign.smells") }}</small>
        <strong>{{ designRiskCount }}</strong>
        <div class="severity-chips">
          <span v-for="item in severityChips" :key="item.key" class="severity-chip">{{ item.key }} {{ item.count }}</span>
        </div>
        <em>{{ generatedAt }}</em>
      </article>
    </section>

    <section class="design-grid">
      <article class="glass-card design-panel matrix-panel">
        <div class="panel-head">
          <span>{{ t("testDesign.matrix") }}</span>
          <small>{{ t("testDesign.matrixMeta") }}</small>
        </div>
        <div class="matrix-shell">
          <table class="design-matrix">
            <thead>
              <tr>
                <th>{{ t("testDesign.risk") }}</th>
                <th v-for="kind in matrixKinds" :key="kind">{{ kind }}</th>
                <th>{{ t("testDesign.total") }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="risk in riskRows"
                :key="risk.key"
                :class="{ active: selectedRisk === risk.key }"
                @click="selectRisk(risk.key)"
              >
                <td>
                  <strong>{{ riskLabel(risk) }}</strong>
                  <code>{{ risk.key }}</code>
                </td>
                <td v-for="kind in matrixKinds" :key="kind">
                  <span class="heat-cell" :style="heatStyle(risk.counts[kind] || 0)">{{ risk.counts[kind] || 0 }}</span>
                </td>
                <td class="font-mono">{{ risk.total }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="!riskRows.length" class="empty-text">{{ t("testDesign.noMatrix") }}</p>
        </div>
      </article>

      <article class="glass-card design-panel graph-panel">
        <div class="panel-head">
          <span>{{ t("testDesign.graph") }}</span>
          <small>{{ graphMeta }}</small>
        </div>
        <div class="graph-lanes">
          <div class="graph-lane">
            <h3>{{ t("testDesign.risks") }}</h3>
            <button
              v-for="risk in riskRows"
              :key="risk.key"
              class="graph-node risk"
              :class="{ active: selectedRisk === risk.key }"
              @click="selectRisk(risk.key)"
            >
              <strong>{{ riskLabel(risk) }}</strong>
              <em>{{ risk.total }}</em>
            </button>
          </div>
          <div class="graph-lane cases">
            <h3>{{ t("testDesign.testCases") }}</h3>
            <button
              v-for="item in visibleCases"
              :key="item.nodeid"
              class="graph-node case"
              :class="{ active: selectedCaseId === item.nodeid }"
              @click="selectedCaseId = item.nodeid"
            >
              <strong>{{ item.name }}</strong>
              <em>{{ item.kind }} · {{ item.assert_count + item.raises_count }}A · {{ item.mock_count }}M</em>
            </button>
            <p v-if="!visibleCases.length" class="empty-text">{{ t("testDesign.noCases") }}</p>
          </div>
          <div class="graph-lane">
            <h3>{{ t("testDesign.targetsTitle") }}</h3>
            <code v-for="target in selectedTargets" :key="target" class="graph-chip">{{ target }}</code>
            <h3>{{ t("testDesign.specsTitle") }}</h3>
            <code v-for="spec in selectedSpecs" :key="spec" class="graph-chip spec">{{ spec }}</code>
          </div>
        </div>
      </article>
    </section>

    <section class="design-detail-grid">
      <article class="glass-card design-panel inspector">
        <div class="panel-head">
          <span>{{ t("testDesign.inspector") }}</span>
          <small>{{ selectedCase?.nodeid || "—" }}</small>
        </div>
        <template v-if="selectedCase">
          <div class="case-title">
            <strong>{{ selectedCase.name }}</strong>
            <span>{{ selectedCase.file }}:{{ selectedCase.line }}</span>
          </div>
          <div class="case-stats">
            <span>{{ selectedCase.kind }}</span>
            <span>{{ t("testDesign.assertions", { count: selectedCase.assert_count }) }}</span>
            <span>{{ t("testDesign.raises", { count: selectedCase.raises_count }) }}</span>
            <span>{{ t("testDesign.mocks", { count: selectedCase.mock_count }) }}</span>
          </div>
          <div class="inspector-columns">
            <div>
              <h3>{{ t("testDesign.risks") }}</h3>
              <code v-for="risk in selectedCase.risks" :key="risk">{{ risk }}</code>
              <h3>{{ t("testDesign.fixtures") }}</h3>
              <code v-for="fixture in selectedCase.fixtures" :key="fixture">{{ fixture }}</code>
            </div>
            <div>
              <h3>{{ t("testDesign.targetsTitle") }}</h3>
              <code v-for="target in selectedCase.target_modules" :key="target">{{ target }}</code>
              <h3>{{ t("testDesign.specsTitle") }}</h3>
              <code v-for="spec in selectedCase.specs" :key="spec">{{ spec }}</code>
            </div>
          </div>
          <div class="case-smells" v-if="selectedCase.smells.length">
            <span v-for="smell in selectedCase.smells" :key="smell">{{ smell }}</span>
          </div>
        </template>
        <p v-else class="empty-text">{{ t("testDesign.noSelectedCase") }}</p>
      </article>

      <article class="glass-card design-panel smell-panel">
        <div class="panel-head">
          <span>{{ t("testDesign.diagnostics") }}</span>
          <small>{{ filteredSmells.length }}</small>
        </div>
        <div class="smell-list">
          <button
            v-for="smell in filteredSmells"
            :key="smell.id"
            class="smell-item"
            :class="smell.severity.toLowerCase()"
            @click="selectCaseFromSmell(smell.subject)"
          >
            <strong>{{ smell.severity }} · {{ smell.title }}</strong>
            <span>{{ smell.subject }}</span>
            <em>{{ smell.recommendation }}</em>
          </button>
          <p v-if="!filteredSmells.length" class="empty-text">{{ t("testDesign.noSmells") }}</p>
        </div>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import type { TestDesignResponse, TestDesignRiskRow } from "../api";
import { useI18n } from "../i18n";
import { formatArtifactDate, heatCellStyle } from "../utils/intelligenceViews";

const { currentLocale, t } = useI18n();
const design = ref<TestDesignResponse | null>(null);
const error = ref("");
const selectedRisk = ref("");
const selectedCaseId = ref("");

const matrixKinds = computed(() => design.value?.matrix.kinds || []);
const riskRows = computed(() => design.value?.matrix.risks || []);
const maxMatrixCount = computed(() => Math.max(1, ...riskRows.value.flatMap(row => matrixKinds.value.map(kind => row.counts[kind] || 0))));
const visibleCases = computed(() => {
  const cases = design.value?.cases || [];
  const filtered = selectedRisk.value ? cases.filter(item => item.risks.includes(selectedRisk.value)) : cases;
  return filtered.slice(0, 80);
});
const selectedCase = computed(() => {
  const cases = design.value?.cases || [];
  return cases.find(item => item.nodeid === selectedCaseId.value) || visibleCases.value[0] || null;
});
const selectedTargets = computed(() => selectedCase.value?.target_modules || []);
const selectedSpecs = computed(() => selectedCase.value?.specs || []);
const filteredSmells = computed(() => {
  const smells = design.value?.smells || [];
  if (!selectedRisk.value) return smells.slice(0, 60);
  const nodeids = new Set(visibleCases.value.map(item => item.nodeid));
  return smells.filter(item => nodeids.has(item.subject) || item.subject === selectedRisk.value).slice(0, 60);
});
const generatedAt = computed(() => formatArtifactDate(design.value?.generated_at || design.value?.latest?.generated_at || "", currentLocale.value));
const graphMeta = computed(() => t("testDesign.graphMeta", { nodes: design.value?.graph.nodes.length ?? 0, links: design.value?.graph.links.length ?? 0 }));
const designRiskCount = computed(() => design.value?.summary.smell_count ?? 0);
const severityChips = computed(() => {
  const counts = design.value?.summary.severity_counts || {};
  return ["P0", "P1", "P2"].map(key => ({ key, count: counts[key] || 0 }));
});

async function load() {
  error.value = "";
  try {
    const next = await api.testDesign();
    design.value = next;
    selectedRisk.value = next.matrix.risks.find(item => item.total > 0)?.key || next.matrix.risks[0]?.key || "";
    selectedCaseId.value = next.cases.find(item => !selectedRisk.value || item.risks.includes(selectedRisk.value))?.nodeid || "";
  } catch (err) {
    error.value = err instanceof Error ? err.message : t("testDesign.loadError");
  }
}

function selectRisk(key: string) {
  selectedRisk.value = selectedRisk.value === key ? "" : key;
  selectedCaseId.value = visibleCases.value[0]?.nodeid || "";
}

function selectCaseFromSmell(subject: string) {
  const cases = design.value?.cases || [];
  const match = cases.find(item => item.nodeid === subject || item.file === subject);
  if (match) selectedCaseId.value = match.nodeid;
}

function riskLabel(risk: TestDesignRiskRow) {
  return currentLocale.value === "en-US" ? risk.label_en || risk.key : risk.label_zh || risk.key;
}

function heatStyle(value: number) {
  return heatCellStyle(value, maxMatrixCount.value, "6, 182, 212", {
    backgroundBase: 0.08,
    backgroundScale: 0.42,
    borderBase: 0.18,
    borderScale: 0.58,
  });
}

onMounted(load);
</script>

<style scoped src="../styles/views/test-design.css"></style>
