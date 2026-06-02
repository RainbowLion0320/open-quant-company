<template>
  <div class="flow-stage glass-card">
    <div v-if="loading" class="pipeline-empty">{{ loadingText }}</div>
    <div v-else-if="payload" class="flow-canvas" :style="canvasStyle">
      <svg
        v-if="visibleArrowPaths.length"
        class="flow-arrows"
        :viewBox="`0 0 ${canvasSize.w} ${canvasSize.h}`"
        :width="canvasSize.w"
        :height="canvasSize.h"
        aria-hidden="true"
      >
        <slot name="arrows" />
      </svg>
      <slot name="nodes" />
    </div>
    <div v-else class="pipeline-empty">{{ emptyText }}</div>
  </div>
</template>

<script setup lang="ts">
import type { CSSProperties } from "vue";
import type { PipelineEdgePath } from "../../utils/pipelineLayout";

defineProps<{
  loading: boolean;
  payload: any | null;
  loadingText: string;
  emptyText: string;
  canvasStyle: CSSProperties;
  canvasSize: { w: number; h: number };
  visibleArrowPaths: PipelineEdgePath[];
}>();
</script>
