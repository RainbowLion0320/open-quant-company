<template>
  <div class="evidence-page">
    <div class="evidence-header">
      <span class="evidence-count">{{ items.length }} strategies</span>
    </div>

    <div v-if="loading" class="evidence-loading">Loading evidence artifacts…</div>
    <div v-else-if="items.length === 0" class="evidence-empty">
      No evidence artifact generated yet. Run research backtest before promotion.
    </div>

    <div v-else class="evidence-grid">
      <div class="evidence-list">
        <div
          v-for="item in items"
          :key="item.strategy"
          class="evidence-row"
          :class="{ active: selected === item.strategy }"
          @click="selected = item.strategy"
        >
          <span class="evidence-name">{{ item.strategy }}</span>
          <span class="evidence-badge" :class="badgeClass(item)">
            {{ badgeLabel(item) }}
          </span>
        </div>
      </div>

      <div v-if="detail" class="evidence-detail">
        <h3>{{ detail.strategy }}</h3>
        <div v-if="detail.parse_error" class="detail-error">Parse error: {{ detail.parse_error }}</div>
        <div v-else-if="!detail.exists" class="detail-missing">No evidence file found.</div>
        <template v-else>
          <div class="detail-section">
            <h4>Promotion Decision</h4>
            <div class="detail-row">
              <span>Status:</span>
              <span :class="detail.summary?.promotion_decision?.passed ? 'text-ok' : 'text-blocked'">
                {{ detail.summary?.promotion_decision?.passed ? 'PASSED' : 'BLOCKED' }}
              </span>
            </div>
            <div v-if="detail.summary?.promotion_decision?.failed_rules?.length" class="detail-row">
              <span>Failed rules:</span>
              <span>{{ detail.summary.promotion_decision.failed_rules.join(', ') }}</span>
            </div>
          </div>
          <div class="detail-section">
            <h4>Metrics</h4>
            <div class="detail-row" v-for="(v, k) in (detail.artifact?.metrics || {})" :key="k">
              <span>{{ k }}:</span>
              <span>{{ typeof v === 'number' ? v.toFixed(4) : v }}</span>
            </div>
          </div>
          <div class="detail-section">
            <h4>OOS</h4>
            <div class="detail-row">
              <span>Months:</span>
              <span>{{ detail.artifact?.oos?.months ?? 0 }}</span>
            </div>
          </div>
          <div class="detail-section">
            <h4>Cost Model</h4>
            <div class="detail-row">
              <span>Commission:</span>
              <span>{{ detail.artifact?.cost_model?.commission ?? 0 }}</span>
            </div>
            <div class="detail-row">
              <span>Slippage:</span>
              <span>{{ detail.artifact?.cost_model?.slippage ?? 0 }}</span>
            </div>
          </div>
          <div class="detail-section" v-if="Object.keys(detail.artifact?.regime_breakdown || {}).length">
            <h4>Regime Breakdown</h4>
            <div class="detail-row" v-for="(v, k) in detail.artifact.regime_breakdown" :key="k">
              <span>{{ k }}:</span>
              <span>{{ JSON.stringify(v) }}</span>
            </div>
          </div>
        </template>
      </div>
      <div v-else class="evidence-detail evidence-detail-empty">
        Select a strategy to view evidence details.
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from "vue";
import { api } from "../api";

const items = ref<any[]>([]);
const detail = ref<any>(null);
const selected = ref<string>("");
const loading = ref(true);

onMounted(async () => {
  try {
    const data = await api.strategyEvidence();
    items.value = data.items || [];
  } catch {
    items.value = [];
  } finally {
    loading.value = false;
  }
});

watch(selected, async (name) => {
  if (!name) { detail.value = null; return; }
  try {
    detail.value = await api.strategyEvidenceDetail(name);
  } catch {
    detail.value = null;
  }
});

function badgeClass(item: any) {
  if (item.parse_error) return "badge-error";
  if (!item.exists) return "badge-missing";
  if (item.promotion_decision === "passed") return "badge-ready";
  if (item.promotion_decision === "blocked") return "badge-blocked";
  return "badge-available";
}

function badgeLabel(item: any) {
  if (item.parse_error) return "parse_error";
  if (!item.exists) return "missing";
  if (item.promotion_decision === "passed") return "promotion_ready";
  if (item.promotion_decision === "blocked") return "blocked";
  return "available";
}
</script>

<style scoped>
.evidence-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.evidence-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.evidence-count {
  font-size: 13px;
  color: var(--text-secondary, #888);
}
.evidence-loading, .evidence-empty {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary, #888);
  font-size: 14px;
}
.evidence-grid {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 12px;
  min-height: 300px;
}
.evidence-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border-right: 1px solid var(--border, #333);
  padding-right: 12px;
}
.evidence-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
}
.evidence-row:hover {
  background: var(--bg-hover, rgba(255,255,255,0.04));
}
.evidence-row.active {
  background: var(--bg-active, rgba(255,255,255,0.08));
}
.evidence-name {
  font-size: 13px;
  font-weight: 500;
}
.evidence-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.badge-missing { background: #333; color: #888; }
.badge-available { background: #1a3a2a; color: #4ade80; }
.badge-ready { background: #1a3a2a; color: #22c55e; }
.badge-blocked { background: #3a1a1a; color: #f87171; }
.badge-error { background: #3a2a1a; color: #fbbf24; }
.evidence-detail {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.evidence-detail-empty {
  color: var(--text-secondary, #888);
  font-size: 14px;
  justify-content: center;
  align-items: center;
}
.evidence-detail h3 {
  font-size: 16px;
  margin: 0;
}
.detail-section h4 {
  font-size: 13px;
  color: var(--text-secondary, #888);
  margin: 0 0 6px 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.detail-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  padding: 2px 0;
}
.detail-row span:first-child {
  color: var(--text-secondary, #888);
}
.text-ok { color: #22c55e; font-weight: 600; }
.text-blocked { color: #f87171; font-weight: 600; }
.detail-error { color: #fbbf24; font-size: 13px; }
.detail-missing { color: #888; font-size: 13px; }
</style>
