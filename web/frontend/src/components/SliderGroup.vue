<template>
  <div class="mb-2.5">
    <div class="flex justify-between mb-1 text-[12px]" style="color:var(--text-quaternary)">
      <span>{{ label }}</span>
      <span style="color:var(--text-secondary)">{{ val }}</span>
    </div>
    <input
      type="range"
      :min="min" :max="max" :step="step"
      :value="model"
      @input="$emit('u', Number(($event.target as HTMLInputElement).value))"
      class="w-full slider"
      :style="{
        accentColor: color || 'var(--accent)',
        '--pct': pct + '%',
      }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  label: string; val: string; model: number;
  min: number; max: number; step?: number; color?: string;
}>();
defineEmits<{ u: [value: number] }>();

const pct = computed(() => {
  const range = props.max - props.min;
  if (range === 0) return 0;
  return ((props.model - props.min) / range) * 100;
});
</script>
