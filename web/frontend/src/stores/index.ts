import { defineStore } from "pinia";
import { ref } from "vue";
import { api } from "../api";

export const useMarketStore = defineStore("market", () => {
  const regime = ref<any>(null);
  const kline = ref<any[]>([]);
  const multiAsset = ref<any[]>([]);
  const macro = ref<any[]>([]);
  const freshness = ref<any>({});
  const updated = ref("");
  const poolSize = ref(0);
  const loading = ref(false);
  const error = ref("");

  async function fetchMarket(range?: string) {
    loading.value = true;
    error.value = "";
    try {
      const data = await api.market(range || "6M");
      regime.value = data.regime;
      kline.value = data.kline;
      multiAsset.value = data.multi_asset || [];
      macro.value = data.macro || [];
      freshness.value = data.freshness || {};
      updated.value = data.updated || "";
      poolSize.value = data.pool_size || 0;
    } catch (e: any) {
      error.value = e.message;
    } finally {
      loading.value = false;
    }
  }

  return {
    regime, kline, multiAsset, macro,
    freshness, updated, poolSize, loading, error, fetchMarket,
  };
});

export const useStrategyStore = defineStore("strategy", () => {
  const strategies = ref<any[]>([]);
  const signals = ref<Record<string, any[]>>({});
  const loading = ref(false);
  const running = ref(false);
  const jobId = ref("");
  const progress = ref(0);
  const progressMsg = ref("");
  const error = ref("");

  async function fetchList() {
    loading.value = true;
    error.value = "";
    try {
      const data = await api.strategies();
      strategies.value = data.strategies || [];
    } catch (e: any) {
      error.value = e?.message || "策略列表加载失败";
    } finally {
      loading.value = false;
    }
  }

  async function fetchSignals(name: string) {
    error.value = "";
    try {
      const data = await api.strategyDetail(name);
      signals.value[name] = data.signals || [];
    } catch (e: any) {
      error.value = e?.message || "策略信号加载失败";
      signals.value[name] = [];
    }
  }

  async function run(strategy: string, limit = 0, params?: any) {
    running.value = true;
    progress.value = 0;
    progressMsg.value = "";
    try {
      const data = await api.strategyRun(strategy, limit, params);
      jobId.value = data.job_id;

      // WebSocket 监听进度
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${protocol}//${window.location.host}/api/strategies/ws/${data.job_id}`);
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        progress.value = msg.progress ?? progress.value;
        progressMsg.value = msg.message || "";
        if (msg.status === "done" || msg.status === "error" || progress.value >= 100) {
          ws.close();
          running.value = false;
          fetchList();
        }
      };
      ws.onerror = () => {
        running.value = false;
        progressMsg.value = "进度连接失败";
      };
    } catch (e: any) {
      running.value = false;
      progressMsg.value = e?.message || "策略运行启动失败";
    }
  }

  return { strategies, signals, loading, running, jobId, progress, progressMsg, error, fetchList, fetchSignals, run };
});
