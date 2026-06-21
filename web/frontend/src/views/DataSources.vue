<template>
  <div class="data-sources view-page">
    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="load">{{ t("common.retry") }}</button>
    </div>

    <section v-if="payload?.status === 'no_artifact'" class="sources-command glass-card">
      <span>{{ t("dataSources.noArtifact") }}</span>
      <code>{{ payload.recommended_command }}</code>
    </section>

    <section class="sources-metrics">
      <article class="source-metric glass-card metric-with-action">
        <button class="artifact-refresh" @click="load" :aria-label="t('dataSources.refresh')">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/>
          </svg>
        </button>
        <small>{{ t("dataSources.sources") }}</small>
        <strong>{{ payload?.summary.source_count ?? 0 }}</strong>
        <em>{{ t("dataSources.audited", { count: payload?.summary.audited_source_count ?? 0 }) }}</em>
      </article>
      <article class="source-metric glass-card">
        <small>{{ t("dataSources.discovered") }}</small>
        <strong>{{ payload?.summary.discovered_count ?? payload?.summary.capability_count ?? 0 }}</strong>
        <em>{{ generatedAt }}</em>
      </article>
      <article class="source-metric glass-card">
        <small>{{ t("dataSources.sampleProbed") }}</small>
        <strong>{{ payload?.summary.sample_probed_count ?? 0 }}</strong>
        <em>{{ t("dataSources.contracted", { count: payload?.summary.contracted_count ?? 0 }) }}</em>
      </article>
      <article class="source-metric glass-card">
        <small>{{ t("dataSources.probeCoverage") }}</small>
        <strong>{{ payload?.summary.probe_ok_count ?? 0 }}</strong>
        <em>{{ t("dataSources.probeBlocked", { count: payload?.summary.probe_blocked_count ?? 0 }) }}</em>
      </article>
      <article class="source-metric glass-card">
        <small>{{ t("dataSources.integrated") }}</small>
        <strong>{{ payload?.summary.project_integrated_count ?? payload?.summary.integrated_count ?? 0 }}</strong>
        <em>{{ t("dataSources.unmapped", { count: payload?.summary.unmapped_count ?? 0 }) }}</em>
      </article>
      <article class="source-metric glass-card">
        <small>{{ t("dataSources.manualReview") }}</small>
        <strong>{{ payload?.summary.manual_review_count ?? payload?.summary.candidate_count ?? 0 }}</strong>
        <em>{{ t("dataSources.tokenGatedWithCount", { count: payload?.summary.requires_token_count ?? 0 }) }}</em>
      </article>
    </section>

    <section class="sources-grid">
      <article class="glass-card source-panel">
        <div class="panel-head">
          <span>{{ t("dataSources.sourceMatrix") }}</span>
          <small>{{ payload?.sources.length ?? 0 }}</small>
        </div>
        <div class="source-list">
          <button
            v-for="row in payload?.sources || []"
            :key="row.source"
            class="source-row"
            :class="{ active: sourceFilter === row.source }"
            @click="sourceFilter = sourceFilter === row.source ? 'all' : row.source"
          >
            <span class="status-dot" :class="sourceStatusClass(row)"></span>
            <strong>{{ row.label }}</strong>
            <code>{{ row.source }}</code>
            <span>{{ row.discovery_scope || row.discovery_method }}</span>
            <em>{{ row.discovered_count ?? row.capability_count }} / {{ row.project_integrated_count ?? row.integrated_count }}</em>
          </button>
        </div>
      </article>

      <article class="glass-card source-panel">
        <div class="panel-head">
          <span>{{ t("dataSources.diffPanel") }}</span>
          <small>{{ diffTotal }}</small>
        </div>
        <div class="diff-list">
          <div v-for="item in diffRows" :key="item.id" class="diff-row">
            <strong>{{ item.kind }}</strong>
            <span>{{ item.title }}</span>
            <code>{{ item.meta }}</code>
          </div>
          <p v-if="!diffRows.length" class="empty-text">{{ t("dataSources.noDiff") }}</p>
        </div>
      </article>
    </section>

    <section class="glass-card source-panel capability-panel">
      <div class="panel-head">
        <span>{{ t("dataSources.capabilityTable") }}</span>
        <small>{{ paginationRange }}</small>
      </div>
      <div class="capability-filter-bar">
        <label>
          <span>{{ t("dataSources.source") }}</span>
          <select v-model="sourceFilter">
            <option value="all">{{ t("dataSources.all") }}</option>
            <option v-for="source in sourceOptions" :key="source" :value="source">{{ source }}</option>
          </select>
        </label>
        <label>
          <span>{{ t("dataSources.usageStatus") }}</span>
          <select v-model="usageStatusFilter">
            <option value="all">{{ t("dataSources.all") }}</option>
            <option v-for="status in usageStatusOptions" :key="status" :value="status">
              {{ capabilityUsageStatusLabel(status) }}
            </option>
          </select>
        </label>
        <label>
          <span>{{ t("dataSources.domain") }}</span>
          <select v-model="domainFilter">
            <option value="all">{{ t("dataSources.all") }}</option>
            <option v-for="domain in domains" :key="domain" :value="domain">{{ domain }}</option>
          </select>
        </label>
      </div>
      <div class="capability-pagination">
        <span>{{ paginationRange }}</span>
        <label>
          <span>{{ t("dataSources.pageSize") }}</span>
          <select v-model.number="pageSize">
            <option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option>
          </select>
        </label>
        <div class="pagination-actions">
          <button class="btn btn-xs" :disabled="currentPage <= 1" @click="currentPage -= 1">
            {{ t("dataSources.prevPage") }}
          </button>
          <strong>{{ t("dataSources.pageIndicator", { page: currentPage, pages: pageCount }) }}</strong>
          <button class="btn btn-xs" :disabled="currentPage >= pageCount" @click="currentPage += 1">
            {{ t("dataSources.nextPage") }}
          </button>
        </div>
      </div>
      <div class="capability-table-wrap">
        <table>
          <thead>
            <tr>
              <th>{{ t("dataSources.source") }}</th>
              <th>{{ t("dataSources.interface") }}</th>
              <th>{{ t("dataSources.asset") }}</th>
              <th>{{ t("dataSources.domain") }}</th>
              <th>{{ t("dataSources.frequency") }}</th>
              <th>{{ t("dataSources.usageStatus") }}</th>
              <th>{{ t("dataSources.issueReason") }}</th>
              <th>{{ t("dataSources.mappedDimensions") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="cap in pagedCapabilities" :key="`${cap.source}:${cap.interface}`">
              <td><span class="source-chip">{{ cap.source }}</span></td>
              <td>
                <strong>{{ cap.interface }}</strong>
                <small>{{ cap.docstring_summary || cap.notes || cap.module || cap.backend || "" }}</small>
              </td>
              <td>{{ cap.asset_type }}</td>
              <td>{{ cap.data_domain }}</td>
              <td>{{ cap.frequency }}</td>
              <td>
                <span class="access-badge" :class="usageStatusClass(capabilityUsageStatus(cap))">
                  {{ capabilityUsageStatusLabel(capabilityUsageStatus(cap)) }}
                </span>
              </td>
              <td><small class="usage-reason">{{ capabilityUsageReason(cap) }}</small></td>
              <td>
                <span v-if="cap.mapped_dimensions.length" class="dimension-list">
                  <code v-for="dim in cap.mapped_dimensions" :key="dim">{{ dim }}</code>
                </span>
                <span v-else class="muted">{{ t("dataSources.notMapped") }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-if="!filteredCapabilities.length" class="empty-text">{{ t("dataSources.noCapabilities") }}</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { api } from "../api";
import type { DataSourceCapability, DataSourceCapabilityResponse, DataSourceCatalogRow } from "../api";
import { useI18n } from "../i18n";

const { currentLocale, t } = useI18n();
const payload = ref<DataSourceCapabilityResponse | null>(null);
const error = ref("");
const sourceFilter = ref("all");
const usageStatusFilter = ref("all");
const domainFilter = ref("all");
const currentPage = ref(1);
const pageSize = ref(100);
const pageSizeOptions = [50, 100, 200];
const usageStatusOptions = ["integrated", "available_unintegrated", "restricted", "pending_validation", "unavailable"] as const;
type UsageStatus = typeof usageStatusOptions[number];

const generatedAt = computed(() => formatDate(payload.value?.generated_at || payload.value?.latest?.generated_at || ""));
const sourceOptions = computed(() => (payload.value?.sources || []).map(item => item.source));
const domains = computed(() => Array.from(new Set((payload.value?.capabilities || []).map(item => item.data_domain))).sort());
const filteredCapabilities = computed(() => (payload.value?.capabilities || []).filter(matchesCapability));
const pageCount = computed(() => Math.max(1, Math.ceil(filteredCapabilities.value.length / pageSize.value)));
const pagedCapabilities = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredCapabilities.value.slice(start, start + pageSize.value);
});
const paginationRange = computed(() => {
  const total = filteredCapabilities.value.length;
  if (!total) return t("dataSources.paginationEmpty");
  const start = (currentPage.value - 1) * pageSize.value + 1;
  const end = Math.min(total, start + pageSize.value - 1);
  return t("dataSources.paginationRange", { start, end, total });
});
const diffSummary = computed(() => payload.value?.diff?.summary || { capability_unmapped_count: 0, registry_missing_source_count: 0, field_frequency_mismatch_count: 0 });
const diffTotal = computed(() => diffSummary.value.capability_unmapped_count + diffSummary.value.registry_missing_source_count + diffSummary.value.field_frequency_mismatch_count);
const diffText = computed(() => [
  `U:${diffSummary.value.capability_unmapped_count}`,
  `R:${diffSummary.value.registry_missing_source_count}`,
  `F:${diffSummary.value.field_frequency_mismatch_count}`,
].join(" · "));
const diffRows = computed(() => {
  const diff = payload.value?.diff;
  if (!diff) return [];
  const unmapped = (diff.capability_unmapped || []).slice(0, 12).map((item: any, idx: number) => ({
    id: `u:${idx}:${item.source}:${item.interface}`,
    kind: t("dataSources.unmappedCapability"),
    title: `${item.source}.${item.interface}`,
    meta: `${item.data_domain || "unknown"} / ${item.frequency || "unknown"}`,
  }));
  const missing = (diff.registry_missing_source || []).slice(0, 12).map((item: any, idx: number) => ({
    id: `r:${idx}:${item.dimension}`,
    kind: t("dataSources.registryMissing"),
    title: item.dimension,
    meta: `${item.source || ""} -> ${item.normalized_source || ""}`,
  }));
  const mismatch = (diff.field_frequency_mismatch || []).slice(0, 12).map((item: any, idx: number) => ({
    id: `f:${idx}:${item.dimension}`,
    kind: t("dataSources.frequencyMismatch"),
    title: item.dimension,
    meta: `${item.registry_frequency || ""} / ${item.capability_frequency || ""}`,
  }));
  return [...unmapped, ...missing, ...mismatch].slice(0, 24);
});

async function load() {
  error.value = "";
  try {
    payload.value = await api.dataSourceCapabilities();
    currentPage.value = 1;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

function matchesCapability(capability: DataSourceCapability) {
  if (sourceFilter.value !== "all" && capability.source !== sourceFilter.value) return false;
  if (domainFilter.value !== "all" && capability.data_domain !== domainFilter.value) return false;
  if (usageStatusFilter.value !== "all" && capabilityUsageStatus(capability) !== usageStatusFilter.value) return false;
  return true;
}

function sourceStatusClass(row: DataSourceCatalogRow) {
  if (!row.capability_count) return "off";
  if (row.access_statuses?.error || row.access_statuses?.missing_secret) return "warn";
  if (row.status === "candidate") return "candidate";
  return "ok";
}

function usageStatusClass(status: UsageStatus) {
  if (status === "integrated") return "ok";
  if (status === "available_unintegrated") return "candidate";
  if (status === "restricted") return "warn";
  if (status === "unavailable") return "danger";
  return "off";
}

function capabilityUsageStatus(capability: DataSourceCapability): UsageStatus {
  const probe = normalizeStatus(capability.probe_status);
  const access = normalizeStatus(capability.access_status);
  const discovery = normalizeStatus(capability.discovery_status);
  const integration = normalizeStatus(capability.integration_status);
  const blockReason = normalizeStatus(capability.probe_block_reason || capability.sample_probe?.block_reason || "");

  if (integration === "project_integrated") return "integrated";
  if (["missing_secret", "no_permission", "rate_limited"].includes(probe) || ["missing_secret", "no_permission", "rate_limited"].includes(access)) {
    return "restricted";
  }
  if (probe === "error" || access === "error" || capability.error_class) return "unavailable";
  if (probe === "ok" || discovery === "sample_probed" || discovery === "contracted" || integration === "contracted" || access === "ok") {
    return "available_unintegrated";
  }
  if (probe === "blocked" && blockReason && !["missing_probe_contract", "unsafe_unbounded_query"].includes(blockReason)) {
    return "unavailable";
  }
  return "pending_validation";
}

function capabilityUsageStatusLabel(status: UsageStatus) {
  return t(`dataSources.usageStatuses.${status}`);
}

function capabilityUsageReason(capability: DataSourceCapability) {
  const status = capabilityUsageStatus(capability);
  const probe = normalizeStatus(capability.probe_status);
  const access = normalizeStatus(capability.access_status);
  const blockReason = normalizeStatus(capability.probe_block_reason || capability.sample_probe?.block_reason || "");

  if (status === "integrated") {
    if (!capability.mapped_dimensions.length) return t("dataSources.reasonIntegrated");
    if (capability.mapped_dimensions.length <= 2) return capability.mapped_dimensions.join(" / ");
    return t("dataSources.reasonMappedCount", { count: capability.mapped_dimensions.length });
  }
  if (status === "available_unintegrated") {
    return capability.row_count != null
      ? t("dataSources.reasonSampleAvailableRows", { count: capability.row_count })
      : t("dataSources.reasonSampleAvailable");
  }
  if (status === "restricted") {
    if (probe === "missing_secret" || access === "missing_secret") return t("dataSources.reasonMissingSecret");
    if (probe === "no_permission" || access === "no_permission") return t("dataSources.reasonNoPermission");
    if (probe === "rate_limited" || access === "rate_limited") return t("dataSources.reasonRateLimited");
    return t("dataSources.reasonRestricted");
  }
  if (status === "unavailable") {
    return capability.error_class || capability.probe_block_reason || capability.sample_probe?.message || t("dataSources.reasonUnavailable");
  }
  if (blockReason === "missing_probe_contract") return t("dataSources.reasonMissingProbeContract");
  if (blockReason === "unsafe_unbounded_query") return t("dataSources.reasonUnsafeProbe");
  if (["manual_review", "candidate"].includes(access) || ["manual_review", "candidate"].includes(probe)) return t("dataSources.reasonManualReview");
  if (capability.discovery_scope || capability.endpoint_pattern || capability.source_url) return t("dataSources.reasonCatalogOnly");
  return t("dataSources.reasonPendingValidation");
}

function normalizeStatus(value: string | undefined | null) {
  return String(value || "").trim().toLowerCase();
}

function formatDate(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(currentLocale.value, {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

watch([sourceFilter, usageStatusFilter, domainFilter, pageSize], () => {
  currentPage.value = 1;
});

watch(pageCount, (pages) => {
  if (currentPage.value > pages) currentPage.value = pages;
});

onMounted(load);
</script>

<style scoped src="../styles/views/data-sources.css"></style>
