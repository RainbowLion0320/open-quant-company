import { computed, ref, onMounted } from "vue";
import { useStrategyStore } from "../stores";
import { useI18n } from "../i18n";
import { signalLabel as formatSignalLabel } from "../utils/signals";
import {
  api,
  type StrategyCatalogItem,
  type StrategyEvaluationSummary,
  type StrategyGovernanceResponse,
} from "../api";

export function useStrategiesView() {

  const store = useStrategyStore();
  const { t } = useI18n();
  const currentStrategy = ref("");
  const signals = ref<any[]>([]);
  const loaded = ref(false);
  const catalog = ref<StrategyCatalogItem[]>([]);
  const governance = ref<StrategyGovernanceResponse | null>(null);
  const evaluation = ref<StrategyEvaluationSummary | null>(null);
  const filters = ref({ lifecycle: "", strategyType: "", layer: "" });

  const strategyColors: Record<string, string> = {
    buffett: "#00d4ff",
    multifactor: "#22c55e",
    cybernetic: "#eab308",
    ml_lgbm: "#7c3aed",
    trend_following: "#38bdf8",
    donchian_breakout: "#f97316",
    rps_relative_strength: "#22c55e",
    sector_rotation: "#06b6d4",
    quality_value: "#84cc16",
    low_vol_defensive: "#a78bfa",
    volume_confirmation: "#facc15",
    regime_gated: "#fb7185",
  };

  const scanByName = computed(() => {
    const map: Record<string, any> = {};
    for (const item of store.strategies) map[item.name] = item;
    return map;
  });

  const filteredCatalog = computed(() => catalog.value.filter(item => {
    if (filters.value.lifecycle && item.lifecycle !== filters.value.lifecycle) return false;
    if (filters.value.strategyType && item.strategy_type !== filters.value.strategyType) return false;
    if (filters.value.layer && item.layer !== filters.value.layer) return false;
    return true;
  }));

  const lifecycleOptions = computed(() => [...new Set(catalog.value.map(item => item.lifecycle))]);
  const typeOptions = computed(() => [...new Set(catalog.value.map(item => item.strategy_type))]);
  const layerOptions = computed(() => [...new Set(catalog.value.map(item => item.layer))]);
  const statusCards = computed(() => {
    const count = (status: string) => catalog.value.filter(item => item.lifecycle === status).length;
    return [
      { key: "total", label: t("strategies.labels.total"), value: catalog.value.length },
      { key: "production", label: lifecycleLabel("production"), value: count("production") },
      { key: "paper", label: lifecycleLabel("paper"), value: count("paper") },
      { key: "candidate", label: lifecycleLabel("candidate"), value: count("candidate") },
    ];
  });

  const paperGateSharpe = computed(() => governance.value?.promotion_rules?.paper?.min_sharpe?.toFixed(2) || "0.50");
  const paperGateDrawdown = computed(() => {
    const v = governance.value?.promotion_rules?.paper?.max_drawdown ?? 0.25;
    return Math.round(v * 100);
  });

  function localizedStrategyLabel(key: string) {
    const messageKey = `strategies.labels.${key}`;
    const label = t(messageKey);
    return label === messageKey ? key : label;
  }
  function lifecycleLabel(status: string) { return localizedStrategyLabel(status); }
  function typeLabel(type: string) { return localizedStrategyLabel(type); }
  function layerLabel(layer: string) { return localizedStrategyLabel(layer); }
  function colorFor(name: string) { return strategyColors[name] || "var(--accent)"; }
  function labelFor(name: string) {
    return catalog.value.find(s => s.name === name)?.label || name;
  }
  function signalLabel(signal: string) {
    return formatSignalLabel(signal, t);
  }
  function scanMeta(name: string) {
    const meta = scanByName.value[name];
    if (!meta) return t("strategies.notScanned");
    const when = meta.last_computed ? meta.last_computed.slice(0, 16) : "";
    return `${t("strategies.scanMeta", { total: meta.total || 0, buys: meta.buys || 0 })}${when ? ` · ${when}` : ""}`;
  }

  async function toggleSignals(name: string) {
    if (currentStrategy.value === name) { currentStrategy.value = ""; signals.value = []; return; }
    currentStrategy.value = name;
    await store.fetchSignals(name);
    signals.value = store.signals[name] || [];
  }

  function runAll() {
    store.run("all", 0, undefined, "production");
  }
  function runCatalogStrategy(item: StrategyCatalogItem) {
    const mode = item.lifecycle === "production" ? "production" : "research";
    const limit = item.lifecycle === "production" ? 0 : 200;
    store.run(item.name, limit, undefined, mode);
  }

  async function reload() {
    loaded.value = false;
    try {
      await Promise.all([store.fetchList(), loadCatalog(), loadGovernance(), loadEvaluation()]);
    } finally {
      loaded.value = true;
    }
  }

  async function loadCatalog() {
    const data = await api.strategyCatalog();
    catalog.value = data.items || [];
  }

  async function loadGovernance() {
    try {
      governance.value = await api.strategyGovernance();
    } catch {
      governance.value = null;
    }
  }

  async function loadEvaluation() {
    try {
      evaluation.value = await api.strategyEvaluation();
    } catch {
      evaluation.value = null;
    }
  }

  onMounted(reload);

  return {
    store,
    t,
    currentStrategy,
    signals,
    loaded,
    catalog,
    governance,
    evaluation,
    filters,
    strategyColors,
    scanByName,
    filteredCatalog,
    lifecycleOptions,
    typeOptions,
    layerOptions,
    statusCards,
    paperGateSharpe,
    paperGateDrawdown,
    localizedStrategyLabel,
    lifecycleLabel,
    typeLabel,
    layerLabel,
    colorFor,
    labelFor,
    signalLabel,
    scanMeta,
    toggleSignals,
    runAll,
    runCatalogStrategy,
    reload,
    loadCatalog,
    loadGovernance,
    loadEvaluation,
  };
}
