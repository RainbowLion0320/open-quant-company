<template>
  <div class="glass-card" :class="glowClass" :style="cardStyle">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(defineProps<{
  glow?: "cyan" | "stellar" | "none";
  padding?: string;
}>(), {
  glow: "none",
  padding: "16px",
});

const glowClass = computed(() => {
  if (props.glow === "cyan") return "glow-cyan";
  if (props.glow === "stellar") return "glow-stellar";
  return "";
});

const cardStyle = computed(() => ({
  padding: props.padding,
}));
</script>
