import type { Ref } from "vue";

export function useAnimatedMetrics() {
  function tweenTo(targetRef: Ref<number> | { value: number }, target: number, decimals = 0, duration = 600) {
    const start = targetRef.value;
    if (start === target) return;
    const startTime = performance.now();

    function tick(now: number) {
      const t = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      const val = start + (target - start) * eased;
      targetRef.value = decimals > 0 ? Number(val.toFixed(decimals)) : Math.round(val);
      if (t < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  }

  return { tweenTo };
}
