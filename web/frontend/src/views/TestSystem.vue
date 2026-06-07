<template>
  <div class="test-system view-page">
    <div class="test-toolbar glass-card">
      <div>
        <h2>{{ t("testSystem.title") }}</h2>
        <p>{{ t("testSystem.subtitle") }}</p>
      </div>
      <button class="icon-button" @click="load" :aria-label="t('testSystem.refresh')">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/></svg>
      </button>
    </div>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="load">{{ t("common.retry") }}</button>
    </div>

    <section class="test-metrics">
      <article class="test-metric glass-card status">
        <span class="status-dot" :class="statusClass"></span>
        <div>
          <small>{{ t("testSystem.currentStatus") }}</small>
          <strong>{{ statusLabel }}</strong>
          <em>{{ latestTime }}</em>
        </div>
      </article>
      <article class="test-metric glass-card">
        <small>{{ t("testSystem.passRate") }}</small>
        <strong>{{ fmtPct(summary?.summary.pass_rate ?? 0) }}</strong>
        <em>{{ totalsText }}</em>
      </article>
      <article class="test-metric glass-card">
        <small>{{ t("testSystem.duration") }}</small>
        <strong>{{ fmtDuration(summary?.summary.duration_seconds ?? 0) }}</strong>
        <em>{{ summary?.latest?.suite || "—" }}</em>
      </article>
      <article class="test-metric glass-card">
        <small>{{ t("testSystem.warnings") }}</small>
        <strong>{{ summary?.summary.warnings ?? 0 }}</strong>
        <em>{{ staleText }}</em>
      </article>
    </section>

    <section class="test-command glass-card" v-if="summary?.recommended_command">
      <span>{{ t("testSystem.command") }}</span>
      <code>{{ summary.recommended_command }}</code>
    </section>

    <section class="domain-grid">
      <button
        v-for="domain in domainList"
        :key="domain.key"
        class="domain-card glass-card"
        :class="{ active: selectedDomain === domain.key }"
        @click="selectedDomain = selectedDomain === domain.key ? '' : domain.key"
      >
        <div class="domain-head">
          <span class="status-dot" :class="domainStatusClass(domain.last_status)"></span>
          <strong>{{ domainLabel(domain) }}</strong>
          <em>{{ domain.last_status }}</em>
        </div>
        <p>{{ domainDescription(domain) }}</p>
        <div class="domain-stats">
          <span>{{ t("testSystem.files", { count: domain.test_count }) }}</span>
          <span>{{ t("testSystem.run", { count: domain.run_count }) }}</span>
          <span>{{ t("testSystem.failed", { count: domain.failed_count }) }}</span>
        </div>
      </button>
    </section>

    <section class="test-detail-grid">
      <article class="glass-card test-panel">
        <div class="panel-head">
          <span>{{ selectedDomainObject ? domainLabel(selectedDomainObject) : t("testSystem.domainDetail") }}</span>
          <small>{{ selectedDomainObject?.key || t("testSystem.allDomains") }}</small>
        </div>
        <div class="detail-columns">
          <div>
            <h3>{{ t("testSystem.testFiles") }}</h3>
            <code v-for="file in selectedFiles" :key="file">{{ file }}</code>
            <p v-if="!selectedFiles.length" class="empty-text">{{ t("testSystem.noFiles") }}</p>
          </div>
          <div>
            <h3>{{ t("testSystem.modules") }}</h3>
            <code v-for="module in selectedDomainObject?.modules || []" :key="module">{{ module }}</code>
            <h3>{{ t("testSystem.specs") }}</h3>
            <code v-for="spec in selectedDomainObject?.specs || []" :key="spec">{{ spec }}</code>
          </div>
        </div>
      </article>

      <article class="glass-card test-panel">
        <div class="panel-head">
          <span>{{ t("testSystem.failures") }}</span>
          <small>{{ latestFailures.length }}</small>
        </div>
        <div class="issue-list">
          <code v-for="item in latestFailures" :key="item">{{ item }}</code>
          <p v-if="!latestFailures.length" class="empty-text">{{ t("testSystem.noFailures") }}</p>
        </div>
      </article>
    </section>

    <section class="glass-card test-panel">
      <div class="panel-head">
        <span>{{ t("testSystem.history") }}</span>
        <small>{{ runs?.total ?? 0 }}</small>
      </div>
      <div class="table-shell compact-table" style="--table-min:760px">
        <table class="data-table">
          <thead>
            <tr>
              <th>{{ t("testSystem.runId") }}</th>
              <th>{{ t("testSystem.suite") }}</th>
              <th>{{ t("testSystem.status") }}</th>
              <th>{{ t("testSystem.total") }}</th>
              <th>{{ t("testSystem.duration") }}</th>
              <th>{{ t("testSystem.finishedAt") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in runs?.runs || []" :key="run.run_id">
              <td class="font-mono">{{ run.run_id }}</td>
              <td>{{ run.suite }}</td>
              <td><span class="history-status" :class="domainStatusClass(run.status)">{{ run.status }}</span></td>
              <td class="font-mono">{{ run.totals.total }}</td>
              <td class="font-mono">{{ fmtDuration(run.duration_seconds) }}</td>
              <td class="font-mono">{{ fmtDate(run.finished_at) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-if="!(runs?.runs?.length)" class="empty-text history-empty">{{ t("testSystem.noRuns") }}</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import type { TestDomain, TestSystemRunsResponse, TestSystemSummaryResponse } from "../api";
import { useI18n } from "../i18n";

const { currentLocale, t } = useI18n();
const summary = ref<TestSystemSummaryResponse | null>(null);
const runs = ref<TestSystemRunsResponse | null>(null);
const error = ref("");
const selectedDomain = ref("");

const domainList = computed(() => summary.value?.domains || []);
const selectedDomainObject = computed(() => domainList.value.find(item => item.key === selectedDomain.value) || null);
const selectedFiles = computed(() => selectedDomainObject.value?.test_files || domainList.value.flatMap(item => item.test_files).slice(0, 24));
const latestFailures = computed(() => summary.value?.latest?.failures || []);
const statusLabel = computed(() => {
  if (!summary.value) return t("testSystem.loading");
  if (summary.value.summary.stale) return t("testSystem.stale");
  return t(`testSystem.statuses.${summary.value.status}`);
});
const statusClass = computed(() => summary.value?.summary.stale ? "stale" : domainStatusClass(summary.value?.status || "loading"));
const latestTime = computed(() => fmtDate(summary.value?.latest?.finished_at || ""));
const totalsText = computed(() => {
  const totals = summary.value?.summary;
  return t("testSystem.totalsText", { passed: totals?.passed ?? 0, failed: totals?.failed ?? 0, total: totals?.total ?? 0 });
});
const staleText = computed(() => summary.value?.summary.stale ? t("testSystem.stale") : t("testSystem.current"));

async function load() {
  error.value = "";
  try {
    const [nextSummary, nextRuns] = await Promise.all([
      api.testSystemSummary(),
      api.testSystemRuns(20),
    ]);
    summary.value = nextSummary;
    runs.value = nextRuns;
    if (!selectedDomain.value && nextSummary.domains.length) selectedDomain.value = nextSummary.domains[0].key;
  } catch (err) {
    error.value = err instanceof Error ? err.message : t("testSystem.loadError");
  }
}

function domainLabel(domain: TestDomain) {
  return currentLocale.value === "en-US" ? domain.label_en : domain.label_zh;
}

function domainDescription(domain: TestDomain) {
  return currentLocale.value === "en-US" ? domain.description_en : domain.description_zh;
}

function domainStatusClass(status: string) {
  if (status === "passed") return "ok";
  if (status === "failed" || status === "error") return "bad";
  if (status === "no_run" || status === "not_run") return "idle";
  if (status === "stale") return "stale";
  return "loading";
}

function fmtPct(value: number) {
  return `${Math.round(value * 100)}%`;
}

function fmtDuration(value: number) {
  if (!value) return "—";
  return value >= 60 ? `${(value / 60).toFixed(1)}m` : `${value.toFixed(1)}s`;
}

function fmtDate(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(currentLocale.value);
}

onMounted(load);
</script>

<style scoped src="../styles/views/test-system.css"></style>
