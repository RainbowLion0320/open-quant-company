<template>
  <div class="data-sources view-page">
    <div class="sources-toolbar glass-card">
      <div>
        <h2>{{ t("dataSources.title") }}</h2>
        <p>{{ t("dataSources.subtitle") }}</p>
      </div>
      <button class="icon-button" @click="load" :aria-label="t('dataSources.refresh')">
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M20 11a8 8 0 0 0-14.9-4M4 7V3m0 4h4m-4 6a8 8 0 0 0 14.9 4M20 17v4m0-4h-4"/>
        </svg>
      </button>
    </div>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="load">{{ t("common.retry") }}</button>
    </div>

    <section v-if="payload?.status === 'no_artifact'" class="sources-command glass-card">
      <span>{{ t("dataSources.noArtifact") }}</span>
      <code>{{ payload.recommended_command }}</code>
    </section>

    <section class="sources-metrics">
      <article class="source-metric glass-card">
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
          <span>{{ t("dataSources.status") }}</span>
          <select v-model="statusFilter">
            <option value="all">{{ t("dataSources.all") }}</option>
            <option value="project_integrated">{{ t("dataSources.projectIntegrated") }}</option>
            <option value="unmapped">{{ t("dataSources.notMapped") }}</option>
            <option value="candidate">{{ t("dataSources.candidate") }}</option>
            <option value="backend_source">{{ t("dataSources.backendSource") }}</option>
          </select>
        </label>
        <label>
          <span>{{ t("dataSources.discoveryStatus") }}</span>
          <select v-model="discoveryFilter">
            <option value="all">{{ t("dataSources.all") }}</option>
            <option v-for="status in discoveryStatuses" :key="status" :value="status">{{ status }}</option>
          </select>
        </label>
        <label>
          <span>{{ t("dataSources.probeStatus") }}</span>
          <select v-model="probeFilter">
            <option value="all">{{ t("dataSources.all") }}</option>
            <option v-for="status in probeStatuses" :key="status" :value="status">{{ status }}</option>
          </select>
        </label>
        <label>
          <span>{{ t("dataSources.blockReason") }}</span>
          <select v-model="blockReasonFilter">
            <option value="all">{{ t("dataSources.all") }}</option>
            <option v-for="reason in blockReasons" :key="reason" :value="reason">{{ reason }}</option>
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
              <th>{{ t("dataSources.discoveryStatus") }}</th>
              <th>{{ t("dataSources.probeStatus") }}</th>
              <th>{{ t("dataSources.blockReason") }}</th>
              <th>{{ t("dataSources.access") }}</th>
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
                <span class="access-badge" :class="discoveryClass(cap.discovery_status)">
                  {{ cap.discovery_status }}
                </span>
                <small>{{ cap.discovery_scope }}</small>
              </td>
              <td>
                <span class="access-badge" :class="accessClass(cap.probe_status)">
                  {{ cap.probe_status }}
                </span>
                <small>{{ probeDetail(cap) }}</small>
              </td>
              <td>
                <code v-if="cap.probe_block_reason">{{ cap.probe_block_reason }}</code>
                <span v-else class="muted">—</span>
              </td>
              <td>
                <span class="access-badge" :class="accessClass(cap.access_status)">
                  {{ cap.access_status }}
                </span>
              </td>
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
const statusFilter = ref("all");
const discoveryFilter = ref("all");
const probeFilter = ref("all");
const blockReasonFilter = ref("all");
const domainFilter = ref("all");
const currentPage = ref(1);
const pageSize = ref(100);
const pageSizeOptions = [50, 100, 200];

const generatedAt = computed(() => formatDate(payload.value?.generated_at || payload.value?.latest?.generated_at || ""));
const sourceOptions = computed(() => (payload.value?.sources || []).map(item => item.source));
const domains = computed(() => Array.from(new Set((payload.value?.capabilities || []).map(item => item.data_domain))).sort());
const discoveryStatuses = computed(() => Array.from(new Set((payload.value?.capabilities || []).map(item => item.discovery_status).filter(Boolean))).sort());
const probeStatuses = computed(() => Array.from(new Set((payload.value?.capabilities || []).map(item => item.probe_status).filter(Boolean))).sort());
const blockReasons = computed(() => Array.from(new Set((payload.value?.capabilities || []).map(item => item.probe_block_reason).filter(Boolean))).sort());
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
  if (discoveryFilter.value !== "all" && capability.discovery_status !== discoveryFilter.value) return false;
  if (probeFilter.value !== "all" && capability.probe_status !== probeFilter.value) return false;
  if (blockReasonFilter.value !== "all" && capability.probe_block_reason !== blockReasonFilter.value) return false;
  if (statusFilter.value === "project_integrated") return capability.integration_status === "project_integrated";
  if (statusFilter.value === "unmapped") return !capability.mapped_dimensions.length;
  if (statusFilter.value !== "all") return capability.integration_status === statusFilter.value || capability.access_status === statusFilter.value;
  return true;
}

function sourceStatusClass(row: DataSourceCatalogRow) {
  if (!row.capability_count) return "off";
  if (row.access_statuses?.error || row.access_statuses?.missing_secret) return "warn";
  if (row.status === "candidate") return "candidate";
  return "ok";
}

function accessClass(status: string) {
  if (["ok", "introspected", "internal"].includes(status)) return "ok";
  if (["candidate", "manual_review", "not_probed"].includes(status)) return "candidate";
  if (["no_permission", "rate_limited", "missing_secret", "error"].includes(status)) return "warn";
  return "off";
}

function discoveryClass(status: string) {
  if (["project_integrated", "contracted"].includes(status)) return "ok";
  if (status === "sample_probed") return "candidate";
  if (status === "discovered") return "off";
  return accessClass(status);
}

function probeDetail(capability: DataSourceCapability) {
  const parts = [
    capability.probe_contract_id,
    capability.row_count != null ? t("dataSources.rows", { count: capability.row_count }) : "",
    capability.elapsed_ms != null ? `${capability.elapsed_ms}ms` : "",
    capability.sample_probe?.message || capability.endpoint_pattern || capability.source_url || "",
  ].filter(Boolean);
  return parts.join(" · ");
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

watch([sourceFilter, statusFilter, discoveryFilter, probeFilter, blockReasonFilter, domainFilter, pageSize], () => {
  currentPage.value = 1;
});

watch(pageCount, (pages) => {
  if (currentPage.value > pages) currentPage.value = pages;
});

onMounted(load);
</script>

<style scoped src="../styles/views/data-sources.css"></style>
