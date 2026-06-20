<template>
  <div class="view-page strategy-data-coverage">
    <div class="compact-action-row">
      <button class="btn btn-sm" @click="load" :disabled="loading">
        {{ loading ? t("common.loading") : t("common.refresh") }}
      </button>
    </div>

    <div v-if="error" class="inline-alert danger">
      <span>{{ error }}</span>
      <button class="btn btn-xs" @click="load">{{ t("common.retry") }}</button>
    </div>

    <div class="catalog-stats">
      <div class="glass-card catalog-stat">
        <span>{{ t("strategies.labels.total") }}</span>
        <strong>{{ summary.strategy_count || 0 }}</strong>
      </div>
      <div class="glass-card catalog-stat">
        <span>{{ t("strategies.requiredGaps") }}</span>
        <strong>{{ summary.required_gap_count || 0 }}</strong>
      </div>
      <div class="glass-card catalog-stat">
        <span>{{ t("strategies.optionalGaps") }}</span>
        <strong>{{ summary.optional_gap_count || 0 }}</strong>
      </div>
      <div class="glass-card catalog-stat">
        <span>{{ t("strategies.missingObservedEvidence") }}</span>
        <strong>{{ summary.missing_observed_count || 0 }}</strong>
      </div>
    </div>

    <div class="coverage-legend compact">
      <span><i class="coverage-dot status-declared"></i>{{ t("strategies.declared") }}</span>
      <span><i class="coverage-dot status-required_missing"></i>{{ t("strategies.requiredMissing") }}</span>
      <span><i class="coverage-dot status-optional_missing"></i>{{ t("strategies.optionalMissing") }}</span>
      <span><i class="coverage-dot status-not_applicable"></i>{{ t("strategies.notApplicable") }}</span>
    </div>

    <div v-if="loading && !payload" class="glass-card card-pad-lg empty-panel">
      {{ t("strategies.loadingCoverage") }}
    </div>

    <div v-else-if="payload" class="table-shell coverage-table-shell" style="--table-min:1180px">
      <table class="data-table coverage-table">
        <thead>
          <tr>
            <th>{{ t("common.strategy") }}</th>
            <th>{{ t("strategies.type") }}</th>
            <th>{{ t("strategies.layer") }}</th>
            <th v-for="family in payload.families" :key="family.key" class="text-center">
              {{ familyLabel(family) }}
            </th>
            <th>{{ t("strategies.coverageNotes") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in payload.rows" :key="row.strategy">
            <td>
              <div class="strategy-cell">
                <span class="strategy-dot" :style="{ background: colorFor(row.strategy), boxShadow: `0 0 8px ${colorFor(row.strategy)}` }"></span>
                <div>
                  <strong>{{ row.label }}</strong>
                  <small>{{ row.strategy }}</small>
                </div>
              </div>
            </td>
            <td>{{ labelFor(row.strategy_type) }}</td>
            <td>{{ labelFor(row.layer) }}</td>
            <td v-for="family in payload.families" :key="`${row.strategy}-${family.key}`" class="text-center">
              <span
                class="coverage-cell"
                :class="`status-${row.cells[family.key]?.status || 'not_applicable'}`"
                :title="cellTitle(row, family.key)"
              >
                {{ cellGlyph(row.cells[family.key]?.status) }}
              </span>
            </td>
            <td>
              <div class="coverage-notes">
                <span v-if="row.missing_required_families.length" class="coverage-note danger">
                  {{ t("strategies.requiredGaps") }}: {{ familyNames(row.missing_required_families) }}
                </span>
                <span v-if="row.optional_missing_families.length" class="coverage-note muted">
                  {{ t("strategies.optionalGaps") }}: {{ familyNames(row.optional_missing_families) }}
                </span>
                <span v-if="row.observed_status === 'missing_evidence'" class="coverage-note muted">
                  {{ t("strategies.missingObservedEvidence") }}
                </span>
                <span v-if="!row.missing_required_families.length" class="coverage-note ok">
                  {{ t("strategies.requiredCoverageOk") }}
                </span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api, type StrategyDataCoverageFamily, type StrategyDataCoverageResponse } from "../api";
import { useI18n } from "../i18n";

const { t, currentLocale } = useI18n();
const payload = ref<StrategyDataCoverageResponse | null>(null);
const loading = ref(false);
const error = ref("");

const strategyColors: Record<string, string> = {
  buffett: "#00d4ff",
  multifactor: "#22c55e",
  cybernetic: "#eab308",
  ml_lgbm: "#7c3aed",
  trend_following: "#38bdf8",
  donchian_breakout: "#f97316",
  rps_relative_strength: "#22c55e",
  sector_rotation: "#06b6d4",
  quality_value: "#84cc16",
  low_vol_defensive: "#a78bfa",
  volume_confirmation: "#facc15",
  regime_gated: "#fb7185",
};

const summary = computed(() => payload.value?.summary || {
  strategy_count: 0,
  family_count: 0,
  required_gap_count: 0,
  optional_gap_count: 0,
  missing_observed_count: 0,
});

const familyNameByKey = computed(() => {
  const out: Record<string, string> = {};
  for (const family of payload.value?.families || []) out[family.key] = familyLabel(family);
  return out;
});

function colorFor(name: string) {
  return strategyColors[name] || "var(--accent)";
}

function labelFor(key: string) {
  const msg = t(`strategies.labels.${key}`);
  return msg === `strategies.labels.${key}` ? key : msg;
}

function familyLabel(family: StrategyDataCoverageFamily) {
  return currentLocale.value.startsWith("zh") ? family.label_zh : family.label_en;
}

function familyNames(keys: string[]) {
  return keys.map(key => familyNameByKey.value[key] || key).join(" / ");
}

function cellGlyph(status = "not_applicable") {
  if (status === "declared") return "✓";
  if (status === "observed") return "◐";
  if (status === "required_missing") return "!";
  if (status === "optional_missing") return "·";
  return "—";
}

function cellTitle(row: any, familyKey: string) {
  const cell = row.cells?.[familyKey];
  const family = familyNameByKey.value[familyKey] || familyKey;
  if (!cell) return family;
  return `${family} · ${t(`strategies.coverageStatus.${cell.status}`)} · ${t(`strategies.coverageExpectation.${cell.expectation}`)}`;
}

async function load() {
  loading.value = true;
  error.value = "";
  try {
    payload.value = await api.strategyDataCoverage();
  } catch (err: any) {
    error.value = err?.message || t("strategies.coverageLoadFailed");
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<style scoped src="../styles/views/strategies.css"></style>
