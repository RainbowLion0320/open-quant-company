<template>
  <div class="regime-panel glass-card">
    <div class="panel-head">
      <span>{{ title }}</span>
    </div>
    <div class="regime-core">
      <div class="regime-orb" :style="{ '--orb-color': regimeColor, '--orb-score': `${displayScore}%` }">
        <div class="regime-orb-inner"></div>
      </div>
      <div class="regime-readout">
        <div class="regime-name" :style="{ color: regimeColor }">{{ regimeLabel }}</div>
        <div class="regime-score-line">
          <strong :style="{ color: regimeColor }">{{ displayScoreText }}</strong>
        </div>
      </div>
    </div>
    <div class="regime-gauge-grid">
      <div
        v-for="(metric, index) in gaugeMetrics"
        :key="metric.key"
        class="regime-gauge-card"
        role="group"
        :aria-label="`${metric.label}: ${metric.value}`"
        :style="{ '--metric-index': index }"
      >
        <div class="mini-gauge" :style="{ '--gauge-color': metric.color, '--gauge-value': `${metric.percent}%` }">
          <span>{{ metric.value }}</span>
        </div>
        <strong>{{ metric.label }}</strong>
      </div>
      <div
        v-for="(item, index) in statusCards"
        :key="item.key"
        class="regime-status-card is-inline"
        :style="{ '--metric-index': index + gaugeMetrics.length }"
      >
        <em>{{ item.label }}</em>
        <strong>{{ item.value }}</strong>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
interface GaugeMetric {
  key: string;
  label: string;
  value: string;
  percent: number;
  color: string;
}

interface StatusCard {
  key: string;
  label: string;
  value: string;
}

defineProps<{
  title: string;
  regimeColor: string;
  regimeLabel: string;
  displayScore: number;
  displayScoreText: string;
  gaugeMetrics: GaugeMetric[];
  statusCards: StatusCard[];
}>();
</script>
