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

<style scoped>
.regime-panel {
  padding: 14px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}
.panel-head span {
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.regime-core {
  display: grid;
  grid-template-columns: 110px 1fr;
  align-items: center;
  gap: 14px;
  padding: 14px 0;
}
.regime-orb {
  width: 100px;
  height: 100px;
  position: relative;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: conic-gradient(var(--orb-color) var(--orb-score), rgba(125,211,252,0.08) 0);
  box-shadow: 0 0 32px rgba(0, 212, 255, 0.12);
}
.regime-orb::before {
  content: "";
  position: absolute;
  inset: 10px;
  border: 1px solid var(--border-default);
  border-radius: 50%;
  background: var(--bg-panel);
}
.regime-orb-inner {
  width: 36px;
  height: 36px;
  z-index: 1;
  border: 1px solid var(--border-strong);
  border-radius: 50%;
  background: radial-gradient(circle, var(--orb-color), transparent 65%);
  animation: orb-breathe 3.2s ease-in-out infinite;
}
@keyframes orb-breathe {
  0%, 100% {
    opacity: 0.9;
    transform: scale(1);
    box-shadow: 0 0 8px var(--orb-color);
  }
  50% {
    opacity: 1;
    transform: scale(1.08);
    box-shadow: 0 0 14px var(--orb-color), 0 0 26px var(--orb-color);
  }
}
.regime-name {
  font-size: 22px;
  line-height: 1;
  font-weight: 750;
  letter-spacing: 0.03em;
}
.regime-readout {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.regime-score-line {
  display: inline-flex;
  min-width: 100%;
  align-items: center;
  justify-content: center;
}
.regime-score-line strong {
  font-family: "JetBrains Mono", monospace;
  font-size: 15px;
  font-weight: 800;
}
.regime-gauge-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.regime-gauge-card,
.regime-status-card {
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.12);
  animation: regime-gauge-enter 420ms cubic-bezier(0.22, 1, 0.36, 1) both;
  animation-delay: calc(var(--metric-index) * 55ms);
}
.regime-gauge-card {
  min-height: 78px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 6px;
  will-change: transform, opacity;
}
.regime-status-card {
  min-height: 28px;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 5px;
  padding: 4px 6px;
}
.regime-status-card em,
.regime-status-card strong {
  min-width: 0;
  line-height: 1;
}
.regime-status-card em {
  flex: 0 1 auto;
  color: var(--text-disabled);
  font-size: 7px;
  font-style: normal;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.regime-status-card strong {
  flex: 1 1 auto;
  overflow: hidden;
  color: var(--text-primary);
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 800;
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@keyframes regime-gauge-enter {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
.mini-gauge {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  position: relative;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: conic-gradient(var(--gauge-color) var(--gauge-value), rgba(125, 211, 252, 0.08) 0);
  box-shadow: 0 0 16px rgba(0, 212, 255, 0.08);
  will-change: background;
}
.mini-gauge::before {
  content: "";
  position: absolute;
  inset: 5px;
  border: 1px solid rgba(125, 211, 252, 0.1);
  border-radius: 50%;
  background: rgba(3, 10, 18, 0.92);
}
.mini-gauge span {
  position: relative;
  z-index: 1;
  color: var(--text-primary);
  font-family: "JetBrains Mono", monospace;
  font-size: 9px;
  font-weight: 750;
}
.regime-gauge-card strong {
  color: var(--text-secondary);
  font-size: 8px;
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: 0.06em;
  text-align: center;
  text-transform: uppercase;
}
@media (max-width: 720px) {
  .regime-core {
    grid-template-columns: 1fr;
    justify-items: center;
    text-align: center;
  }
  .regime-readout {
    align-items: center;
  }
}
@media (prefers-reduced-motion: reduce) {
  .regime-orb-inner,
  .regime-gauge-card,
  .regime-status-card {
    animation: none;
  }
}
</style>
