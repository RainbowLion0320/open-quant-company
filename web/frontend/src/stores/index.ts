import { defineStore } from "pinia";
import { ref } from "vue";
import { api, type PositionCapacity } from "../api";
import { translate } from "../i18n";

export const useMarketStore = defineStore("market", () => {
  const regime = ref<any>(null);
  const kline = ref<any[]>([]);
  const multiAsset = ref<any[]>([]);
  const assetPulse = ref<any[]>([]);
  const assetModules = ref<any[]>([]);
  const freshness = ref<any>({});
  const updated = ref("");
  const poolSize = ref(0);
  const positionCapacity = ref<PositionCapacity>({ current: 0, max: 0 });
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
      assetPulse.value = data.asset_pulse || [];
      assetModules.value = data.asset_modules || [];
      freshness.value = data.freshness || {};
      updated.value = data.updated || "";
      poolSize.value = data.pool_size || 0;
      positionCapacity.value = data.position_capacity || {
        current: data.pool_size || 0,
        max: Math.max(data.pool_size || 0, 1),
      };
    } catch (e: any) {
      error.value = e?.message || translate("errors.marketLoad");
    } finally {
      loading.value = false;
    }
  }

  return {
    regime, kline, multiAsset, assetPulse, assetModules,
    freshness, updated, poolSize, positionCapacity, loading, error, fetchMarket,
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
      error.value = e?.message || translate("errors.strategyListLoad");
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
      error.value = e?.message || translate("errors.strategySignalLoad");
      signals.value[name] = [];
    }
  }

  async function run(strategy: string, limit = 0, params?: any, mode: "production" | "research" = "production") {
    running.value = true;
    progress.value = 0;
    progressMsg.value = "";
    try {
      const data = await api.strategyRun(strategy, limit, params, mode);
      jobId.value = data.job_id;

      // Listen for strategy run progress over WebSocket.
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
        progressMsg.value = translate("errors.progressConnection");
      };
    } catch (e: any) {
      running.value = false;
      progressMsg.value = e?.message || translate("errors.strategyRunStart");
    }
  }

  return { strategies, signals, loading, running, jobId, progress, progressMsg, error, fetchList, fetchSignals, run };
});
