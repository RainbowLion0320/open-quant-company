import { ref, computed, onMounted } from "vue";
import { api } from "../api";
import { useI18n } from "../i18n";
import type {
  SectorOverviewResponse,
  SectorCard,
} from "../api";
import { colorBySignedRatio, fmtRatioPct as fmtPct } from "../utils/format";
import { clampNumber, dataSourceLabel, formatAmount, signalPower } from "../utils/sector";

export function useSectorsView() {

  const loading = ref(false);
  const { t } = useI18n();
  const error = ref("");
  const overview = ref<SectorOverviewResponse | null>(null);
  const activeSector = ref("");
  type BlockHeatMode = "capital" | "momentum" | "signal";

  const blockHeatMode = ref<BlockHeatMode>("capital");
  const blockHeatModes = computed<{ key: BlockHeatMode; label: string; metric: string }[]>(() => [
    { key: "capital", label: t("sectors.modes.capital.label"), metric: t("sectors.modes.capital.metric") },
    { key: "momentum", label: t("sectors.modes.momentum.label"), metric: t("sectors.modes.momentum.metric") },
    { key: "signal", label: t("sectors.modes.signal.label"), metric: t("sectors.modes.signal.metric") },
  ]);

  type SectorBlockTile = {
    sector: SectorCard;
    size: number;
    sizeRatio: number;
    span: number;
    metric: number;
    metricLabel: string;
  };

  const sortedSectors = computed(() => {
    if (!overview.value) return [];
    return [...overview.value.sectors].sort((a, b) => a.rank - b.rank);
  });

  const top5Return = computed(() => {
    const top = sortedSectors.value.slice(0, 5);
    if (!top.length) return "0.00";
    const avg = top.reduce((s, x) => s + x.return_5d, 0) / top.length;
    return (avg * 100).toFixed(2);
  });

  const bottom5Return = computed(() => {
    const bot = sortedSectors.value.slice(-5);
    if (!bot.length) return "0.00";
    const avg = bot.reduce((s, x) => s + x.return_5d, 0) / bot.length;
    return (avg * 100).toFixed(2);
  });

  const activeBlockHeatMode = computed(() => blockHeatModes.value.find(m => m.key === blockHeatMode.value));

  const capitalSourceLabel = computed(() => dataSourceLabel(overview.value?.capital_source || "missing"));

  const blockSizeLabel = computed(() => (
    sortedSectors.value.some(s => Number(s.amount_5d_avg || 0) > 0)
      ? t("sectors.blockSizeTurnover")
      : t("sectors.blockSizeFallback")
  ));

  const capitalConcentration = computed(() => {
    const sectors = [...sortedSectors.value].sort((a, b) => tileSize(b) - tileSize(a));
    const total = sectors.reduce((sum, sector) => sum + tileSize(sector), 0);
    if (!total) return "—";
    const top5 = sectors.slice(0, 5).reduce((sum, sector) => sum + tileSize(sector), 0);
    return `${((top5 / total) * 100).toFixed(1)}%`;
  });

  const sectorBlockTiles = computed<SectorBlockTile[]>(() => {
    const items = sortedSectors.value
      .map(sector => ({ sector, size: tileSize(sector) }))
      .filter(item => item.size > 0)
      .sort((a, b) => b.size - a.size);
    const maxSize = items[0]?.size || 1;
    return items.map(item => {
      const sizeRatio = clampNumber(item.size / maxSize, 0, 1);
      const span = sectorBlockSpan(item.size, maxSize);
      return {
        ...item,
        sizeRatio,
        span,
        metric: blockMetric(item.sector),
        metricLabel: blockMetricLabel(item.sector),
      };
    });
  });

  const perfDate = computed(() => {
    const f = overview.value?.freshness?.performance || "";
    const m = f.match(/(\d{4}-\d{2}-\d{2})|(\d{8})/);
    if (!m) return "—";
    const raw = m[1] || m[2];
    return raw.length === 8 ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6)}` : raw;
  });

  const activeDetail = computed(() => {
    if (!activeSector.value || !overview.value) return null;
    return overview.value.sectors.find(s => s.sector_code === activeSector.value) || null;
  });

  function colorPct(v: number) {
    return colorBySignedRatio(v);
  }

  function tileSize(sector: SectorCard) {
    const amount = Number(sector.amount_5d_avg || sector.turnover_amount || 0);
    if (amount > 0) return amount;
    return Math.max(Number(sector.member_count || 0), 1);
  }

  function blockMetric(sector: SectorCard) {
    if (blockHeatMode.value === "momentum") return Number(sector.return_20d || 0);
    if (blockHeatMode.value === "signal") return signalPower(sector) - 0.5;
    return Number(sector.return_5d || 0);
  }

  function blockMetricLabel(sector: SectorCard) {
    if (blockHeatMode.value === "signal") return `${(signalPower(sector) * 100).toFixed(0)}% buy`;
    return fmtPct(blockHeatMode.value === "momentum" ? sector.return_20d : sector.return_5d);
  }

  function sectorBlockSpan(size: number, maxSize: number) {
    if (maxSize <= 0) return 1;
    const ratio = clampNumber(size / maxSize, 0, 1);
    return clampNumber(Math.ceil(Math.sqrt(ratio) * 4 - 0.15), 1, 4);
  }

  function industryNameFontSize(sizeRatio: number) {
    const visualWeight = Math.pow(clampNumber(sizeRatio, 0, 1), 0.8);
    return `${(12 + visualWeight * 18).toFixed(1)}px`;
  }

  function industryTooltip(tile: SectorBlockTile) {
    // Static contract anchor: 行业代码
    const code = tile.sector.sector_code || "SW1";
    return `${tile.sector.sector_name} · ${t("sectors.industryCode")} ${code} · ${blockSizeLabel.value} ${formatAmount(tile.size)} · ${activeBlockHeatMode.value?.metric}: ${tile.metricLabel}`;
  }

  function heatStyle(metric: number) {
    const abs = Math.min(Math.abs(metric) * 7, 0.48);
    if (metric > 0) {
      return {
        backgroundColor: `rgba(21, 128, 61, ${0.18 + abs})`,
        border: `rgba(34, 197, 94, ${0.24 + abs * 0.72})`,
        boxShadow: `inset 0 0 0 1px rgba(187, 247, 208, ${0.04 + abs * 0.14}), inset 0 -28px 68px rgba(2, 6, 13, 0.18)`,
        color: "var(--positive)",
      };
    }
    if (metric < 0) {
      return {
        backgroundColor: `rgba(153, 27, 27, ${0.18 + abs})`,
        border: `rgba(248, 113, 113, ${0.24 + abs * 0.72})`,
        boxShadow: `inset 0 0 0 1px rgba(254, 202, 202, ${0.04 + abs * 0.14}), inset 0 -28px 68px rgba(2, 6, 13, 0.18)`,
        color: "var(--negative)",
      };
    }
    return {
      backgroundColor: "rgba(15, 23, 42, 0.72)",
      border: "rgba(125, 211, 252, 0.18)",
      boxShadow: "inset 0 0 0 1px rgba(125, 211, 252, 0.04), inset 0 -28px 68px rgba(2, 6, 13, 0.16)",
      color: "var(--text-secondary)",
    };
  }

  function industryBlockStyle(tile: SectorBlockTile) {
    const tone = heatStyle(tile.metric);
    return {
      gridColumn: `span ${tile.span}`,
      gridRow: `span ${tile.span}`,
      backgroundColor: tone.backgroundColor,
      borderColor: activeSector.value === tile.sector.sector_code ? "var(--accent)" : tone.border,
      boxShadow: tone.boxShadow,
      color: tone.color,
      "--industry-name-size": industryNameFontSize(tile.sizeRatio),
    };
  }

  function toggleSector(s: SectorCard) {
    if (activeSector.value === s.sector_code) {
      activeSector.value = "";
      return;
    }
    activeSector.value = s.sector_code;
  }

  async function fetchData() {
    loading.value = true;
    error.value = "";
    try {
      overview.value = await api.sectorOverview();
    } catch (e: any) {
      error.value = e?.message || t("sectors.loadError");
      overview.value = null;
    }
    loading.value = false;
  }

  onMounted(fetchData);

  return {
    loading,
    t,
    error,
    overview,
    activeSector,
    blockHeatMode,
    blockHeatModes,
    sortedSectors,
    top5Return,
    bottom5Return,
    activeBlockHeatMode,
    capitalSourceLabel,
    blockSizeLabel,
    capitalConcentration,
    sectorBlockTiles,
    perfDate,
    activeDetail,
    fmtPct,
    colorPct,
    tileSize,
    blockMetric,
    blockMetricLabel,
    sectorBlockSpan,
    industryNameFontSize,
    dataSourceLabel,
    formatAmount,
    industryTooltip,
    heatStyle,
    industryBlockStyle,
    toggleSector,
    fetchData,
  };
}
