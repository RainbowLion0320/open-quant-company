<template>
  <div class="asset-coverage">
    <div v-if="loading" class="loading">Loading asset coverage…</div>
    <div v-else-if="items.length === 0" class="empty">No asset data available.</div>
    <div v-else class="asset-table-wrap">
      <table class="asset-table">
        <thead>
          <tr>
            <th>Asset Type</th>
            <th>Label</th>
            <th>Enabled</th>
            <th>Data Source</th>
            <th>Research Ready</th>
            <th>Tradable</th>
            <th>Universe Size</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.asset_type">
            <td class="mono">{{ item.asset_type }}</td>
            <td>{{ item.label }}</td>
            <td>
              <span class="badge" :class="item.enabled ? 'badge-ok' : 'badge-off'">
                {{ item.enabled ? 'enabled' : 'disabled' }}
              </span>
            </td>
            <td>
              <span class="badge" :class="sourceBadge(item.data_source)">
                {{ item.data_source }}
              </span>
            </td>
            <td>
              <span class="badge" :class="item.research_ready ? 'badge-ok' : 'badge-off'">
                {{ item.research_ready ? '✓' : '✗' }}
              </span>
            </td>
            <td>
              <span class="badge" :class="item.tradable ? 'badge-ok' : 'badge-warn'">
                {{ item.tradable ? '✓' : '✗' }}
              </span>
            </td>
            <td class="num">{{ item.universe_size }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { api } from "../api";

const items = ref<any[]>([]);
const loading = ref(true);

onMounted(async () => {
  try {
    const data = await api.assetsOverview();
    items.value = data.items || [];
  } catch {
    items.value = [];
  } finally {
    loading.value = false;
  }
});

function sourceBadge(source: string) {
  if (source === "real") return "badge-ok";
  if (source === "proxy") return "badge-warn";
  return "badge-off";
}
</script>

<style scoped>
.asset-coverage {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.loading, .empty {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary, #888);
}
.asset-table-wrap {
  overflow-x: auto;
}
.asset-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.asset-table th {
  text-align: left;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border, #333);
  color: var(--text-secondary, #888);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-size: 11px;
}
.asset-table td {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border, #222);
}
.asset-table tr:hover {
  background: var(--bg-hover, rgba(255,255,255,0.02));
}
.mono {
  font-family: monospace;
  font-size: 12px;
}
.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}
.badge-ok { background: #1a3a2a; color: #4ade80; }
.badge-warn { background: #3a3a1a; color: #fbbf24; }
.badge-off { background: #2a2a2a; color: #666; }
</style>
