import { defineStore } from "pinia";
import { ref } from "vue";

export const useMarketStore = defineStore("market", () => {
  const regime = ref<any>(null);
  const kline = ref<any[]>([]);
  const config = ref<any>({});
  const registry = ref<any[]>([]);
  const loading = ref(false);
  const error = ref("");

  async function fetchMarket() {
    loading.value = true;
    error.value = "";
    try {
      const res = await window.fetch("/api/market");
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      regime.value = data.regime;
      kline.value = data.kline;
      config.value = data.config;
      registry.value = data.registry || [];
    } catch (e: any) {
      error.value = e.message;
    } finally {
      loading.value = false;
    }
  }

  return { regime, kline, config, registry, loading, error, fetchMarket };
});

export const useStrategyStore = defineStore("strategy", () => {
  const strategies = ref<any[]>([]);
  const signals = ref<Record<string, any[]>>({});
  const loading = ref(false);
  const running = ref(false);
  const jobId = ref("");
  const progress = ref(0);
  const progressMsg = ref("");

  async function fetchList() {
    const data = await (await window.fetch("/api/strategies")).json();
    strategies.value = data.strategies || [];
  }

  async function fetchSignals(name: string) {
    const data = await (await window.fetch(`/api/strategies/${name}`)).json();
    signals.value[name] = data.signals || data || [];
  }

  async function run(strategy: string, limit = 0, params?: any) {
    running.value = true;
    progress.value = 0;
    const res = await fetch("/api/strategies/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy, limit, params }),
    });
    const data = await res.json();
    jobId.value = data.job_id;

    // WebSocket 监听进度
    const ws = new WebSocket(`ws://localhost:8501/ws/strategies/${data.job_id}`);
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      progress.value = msg.progress;
      progressMsg.value = msg.message;
      if (msg.progress >= 100) {
        ws.close();
        running.value = false;
        fetchList();
      }
    };
  }

  return { strategies, signals, loading, running, jobId, progress, progressMsg, fetchList, fetchSignals, run };
});
