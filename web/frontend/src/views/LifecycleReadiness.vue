<template>
  <div class="lifecycle-readiness view-page">
    <section v-if="error" class="lifecycle-alert danger">{{ error }}</section>

    <section class="lifecycle-summary">
      <article class="summary-tile metric-with-action" :class="statusClass">
        <button class="artifact-refresh" @click="load" :disabled="loading" :aria-label="t('common.refresh')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/></svg>
        </button>
        <span>{{ t("lifecycle.status") }}</span>
        <strong>{{ payload?.status || "unknown" }}</strong>
      </article>
      <article class="summary-tile">
        <span>{{ t("lifecycle.blockers") }}</span>
        <strong>{{ blockers.length }}</strong>
      </article>
      <article class="summary-tile">
        <span>{{ t("lifecycle.warnings") }}</span>
        <strong>{{ warnings.length }}</strong>
      </article>
      <article class="summary-tile">
        <span>{{ t("lifecycle.updated") }}</span>
        <strong>{{ payload?.latest?.generated_at || "-" }}</strong>
      </article>
    </section>

    <section v-if="payload?.status === 'no_artifact'" class="lifecycle-empty">
      <strong>{{ t("lifecycle.noArtifact") }}</strong>
      <code>{{ payload.recommended_command }}</code>
    </section>

    <section class="lifecycle-grid">
      <article v-for="check in checkCards" :key="check.key" class="check-card">
        <div class="check-card-head">
          <span>{{ check.label }}</span>
          <strong :class="statusClassFor(check.status)">{{ check.status }}</strong>
        </div>
        <div class="check-meta">
          <span v-for="line in check.lines" :key="line">{{ line }}</span>
        </div>
      </article>
    </section>

    <section class="lifecycle-lists">
      <article>
        <h3>{{ t("lifecycle.blockerList") }}</h3>
        <p v-if="!blockers.length" class="muted">{{ t("lifecycle.none") }}</p>
        <ul v-else>
          <li v-for="item in blockers" :key="item"><code>{{ item }}</code></li>
        </ul>
      </article>
      <article>
        <h3>{{ t("lifecycle.warningList") }}</h3>
        <p v-if="!warnings.length" class="muted">{{ t("lifecycle.none") }}</p>
        <ul v-else>
          <li v-for="item in warnings" :key="item"><code>{{ item }}</code></li>
        </ul>
      </article>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "../api";
import type { LifecycleResponse } from "../api";
import { useI18n } from "../i18n";

const { t } = useI18n();
const payload = ref<LifecycleResponse | null>(null);
const loading = ref(false);
const error = ref("");

const blockers = computed(() => payload.value?.blockers || []);
const warnings = computed(() => payload.value?.warnings || []);
const statusClass = computed(() => statusClassFor(payload.value?.status || ""));

const checkCards = computed(() => {
  const checks = payload.value?.checks || {};
  return Object.entries(checks).map(([key, value]) => {
    const status = String(value.status || "unknown");
    const summary = value.summary && typeof value.summary === "object" ? value.summary : {};
    const lines = Object.entries(summary).slice(0, 4).map(([name, val]) => `${name}: ${String(val)}`);
    if (Array.isArray(value.blockers) && value.blockers.length) {
      lines.push(`blockers: ${value.blockers.length}`);
    }
    return {
      key,
      label: t(`lifecycle.checks.${key}`),
      status,
      lines,
    };
  });
});

function statusClassFor(status: string) {
  if (status === "ok") return "ok";
  if (status === "blocked" || status === "missing" || status === "not_integrated") return "blocked";
  if (status === "no_artifact") return "unknown";
  return "warn";
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    payload.value = await api.lifecycle();
  } catch (err) {
    error.value = err instanceof Error ? err.message : t("errors.loadFailed");
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped src="../styles/views/lifecycle-readiness.css"></style>
