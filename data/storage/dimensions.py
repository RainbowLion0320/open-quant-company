"""
Data Dimension Registry — 统一数据维度管理

Like StrategyRegistry: single source of truth for what data exists.
配置: config/settings.yaml → data_registry

用法:
  from data.storage.dimensions import get_registry, is_available
  reg = get_registry()
  dims = reg.get_enabled()  # 所有已启用的维度
  reg.get("holder_number")  # 单个维度详情
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from core.settings import get_section


ALLOWED_SOURCES = {"akshare", "tushare_free", "tushare_paid", "future", "computed", "system"}
ALLOWED_ASSETS = {"stock", "macro", "fund", "futures", "crypto", "bond", "system", "sector"}
ALLOWED_STATUSES = {"available", "rate_limited", "paid", "planned"}
ALLOWED_FREQS = {"daily", "monthly", "quarterly", "event", "minute", "intraday", "system"}
ALLOWED_REPAIR_POLICIES = {"auto", "rate_limited", "manual", "none"}

SOURCE_LABELS = {
    "akshare": "AKShare",
    "tushare_free": "Tushare",
    "tushare_paid": "Tushare Paid",
    "future": "Future",
    "computed": "Computed",
    "system": "System",
}

DEFAULT_HEALTH_TABLES = {
    "stock_basic": "stock_basic",
    "trade_cal": "trade_cal",
    "tushare_stock_daily": "tushare_stock_daily",
    "ohlcv_daily": "stock_daily",
    "ohlcv_daily_raw": "stock_daily_raw",
    "ohlcv_daily_hfq": "stock_daily_hfq",
    "adj_factor": "stock_adj_factor",
    "corporate_actions": "stock_corporate_actions",
    "financial_summary": "stock_financials",
    "fina_indicator": "stock_fina_indicator",
    "income_statement": "stock_income_statement",
    "balance_sheet": "stock_balance_sheet",
    "cashflow_statement": "stock_cashflow_statement",
    "valuation_daily": "stock_valuation",
    "moneyflow_monthly": "stock_moneyflow_monthly",
    "moneyflow_mkt_dc": "stock_moneyflow_mkt_dc",
    "moneyflow_daily": "stock_moneyflow_daily",
    "moneyflow_tushare_daily": "stock_moneyflow_tushare_daily",
    "holder_number": "stock_holders",
    "holder_trade": "stock_holdertrade",
    "limit_list": "stock_limit_list",
    "top_list": "stock_top_list",
    "broker_recommend": "stock_broker_recommend",
    "research_report": "stock_research_report",
    "dividend": "stock_dividend",
    "fund_basic": "fund_basic",
    "cyq_perf": "stock_cyq_perf",
    "sector_sw_daily": "sector_sw_daily",
    "sector_membership": "sector_membership",
    "sector_performance_snapshot": "sector_performance_snapshot",
    "sector_signal_snapshot": "sector_signal_snapshot",
    "sector_exposure_snapshot": "sector_exposure_snapshot",
}

FRESHNESS_SLA_BY_FREQ = {
    "daily": 5,
    "monthly": 45,
    "quarterly": 140,
    "event": 365,
    "minute": 1,
    "intraday": 1,
    "system": 2,
}

PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9_]+)\}")


@dataclass(frozen=True)
class HealthTableMeta:
    """Metadata consumed by DB Health and Web system APIs."""

    table: str
    source: str
    label_zh: str
    repairable: bool = False
    registry_key: str = ""
    freshness_sla_days: Optional[int] = None
    repair_policy: str = "none"
    partition_key: str = ""


COMPUTED_HEALTH_META: dict[str, HealthTableMeta] = {
    "signals_buffett": HealthTableMeta("signals_buffett", "Computed (策略生成)", "巴菲特价值信号"),
    "signals_buffett_scan": HealthTableMeta("signals_buffett_scan", "Computed (策略生成)", "巴菲特全量扫描"),
    "signals_multifactor": HealthTableMeta("signals_multifactor", "Computed (策略生成)", "多因子打分信号"),
    "signals_ml_lgbm": HealthTableMeta("signals_ml_lgbm", "Computed (策略生成)", "LightGBM 机器学习信号"),
    "signals_cybernetic": HealthTableMeta("signals_cybernetic", "Computed (策略生成)", "控制论自适应信号"),
    "paper_trades": HealthTableMeta("paper_trades", "PaperBroker (模拟)", "模拟交易记录"),
    "paper_nav": HealthTableMeta("paper_nav", "PaperBroker (模拟)", "模拟交易净值"),
    "paper_state": HealthTableMeta("paper_state", "PaperBroker (模拟)", "模拟账户状态"),
    "system_llm_usage": HealthTableMeta(
        "system_llm_usage", "LLM Providers", "本项目 LLM provider API 用量账本",
        freshness_sla_days=2, repair_policy="manual", partition_key="utc_date",
    ),
    "features_all": HealthTableMeta("features_all", "Computed (多源融合)", "PIT 特征切片 (全量)", partition_key="month"),
    "cache_api_calls": HealthTableMeta("cache_api_calls", "AKShare Cache (可重建)", "API 响应缓存 (MD5)"),
}


def _infer_partition_key(cache: str) -> str:
    placeholders = PLACEHOLDER_RE.findall(cache or "")
    if not placeholders:
        return "file" if cache else ""
    first = placeholders[0]
    return {
        "YYYYMMDD": "trade_date",
        "YYYYMM": "month",
        "report_date": "report_date",
    }.get(first, first)


def _default_repair_policy(status: str) -> str:
    if status == "rate_limited":
        return "rate_limited"
    if status == "available":
        return "auto"
    return "none"


def _default_sla(freq: str, status: str) -> Optional[int]:
    if status in {"paid", "planned"}:
        return None
    return FRESHNESS_SLA_BY_FREQ.get(freq)


@dataclass
class DataDimension:
    """One data dimension — a single column in the feature store."""
    key: str
    source: str           # akshare | tushare_free | tushare_paid | future
    asset: str            # stock | macro | fund | futures | crypto
    status: str           # available | rate_limited | paid | planned
    freq: str             # daily | monthly | quarterly | event | minute
    enabled: bool
    label: str
    cache: str            # relative path pattern
    description: str = ""
    health_table: str = ""
    health_label: str = ""
    freshness_sla_days: Optional[int] = None
    repair_policy: str = "none"
    partition_key: str = ""
    health_enabled: bool = True
    health_max_sample: int = 30
    # P1-8: DataContract integration
    schema_version: int = 1
    contract_path: str = ""

    @property
    def is_available(self) -> bool:
        return self.status == "available" and self.enabled

    @property
    def is_rate_limited(self) -> bool:
        return self.status == "rate_limited" and self.enabled

    @property
    def is_paid(self) -> bool:
        return self.status == "paid"

    @property
    def is_planned(self) -> bool:
        return self.status == "planned"


class DataRegistry:
    """Central registry of all data dimensions."""

    def __init__(self):
        self._dimensions: Dict[str, DataDimension] = {}
        self._load()

    def _load(self):
        registry_cfg = get_section("data_registry", {}) or {}
        for key, info in registry_cfg.items():
            health = info.get("health", {}) or {}
            freq = info.get("freq", "daily")
            status = info.get("status", "planned")
            cache = info.get("cache", "")
            self._dimensions[key] = DataDimension(
                key=key,
                source=info.get("source", ""),
                asset=info.get("asset", ""),
                status=status,
                freq=freq,
                enabled=info.get("enabled", False),
                label=info.get("label", key),
                cache=cache,
                description=info.get("description", ""),
                health_table=health.get("table") or info.get("health_table") or DEFAULT_HEALTH_TABLES.get(key, key),
                health_label=health.get("label") or info.get("health_label") or info.get("label", key),
                freshness_sla_days=health.get("freshness_sla_days", info.get("freshness_sla_days", _default_sla(freq, status))),
                repair_policy=health.get("repair_policy") or info.get("repair_policy") or _default_repair_policy(status),
                partition_key=health.get("partition_key") or info.get("partition_key") or _infer_partition_key(cache),
                health_enabled=health.get("enabled", info.get("health_enabled", True)),
                health_max_sample=int(health.get("max_sample", info.get("health_max_sample", 30))),
            )

    def get(self, key: str) -> Optional[DataDimension]:
        return self._dimensions.get(key)

    def get_enabled(self) -> List[DataDimension]:
        """All dimensions with enabled=True."""
        return [d for d in self._dimensions.values() if d.enabled]

    def get_available(self) -> List[DataDimension]:
        """Dimensions ready to use (available + enabled)."""
        return [d for d in self._dimensions.values() if d.is_available]

    def get_rate_limited(self) -> List[DataDimension]:
        """Dimensions that need background cron fetching."""
        return [d for d in self._dimensions.values() if d.is_rate_limited]

    def get_planned(self) -> List[DataDimension]:
        """Dimensions that are planned but not yet implemented."""
        return [d for d in self._dimensions.values() if d.is_planned]

    def get_paid(self) -> List[DataDimension]:
        """Dimensions requiring higher Tushare积分."""
        return [d for d in self._dimensions.values() if d.is_paid]

    def by_asset(self, asset: str) -> List[DataDimension]:
        return [d for d in self._dimensions.values() if d.asset == asset]

    def by_source(self, source: str) -> List[DataDimension]:
        return [d for d in self._dimensions.values() if d.source == source]

    @property
    def all(self) -> Dict[str, DataDimension]:
        return dict(self._dimensions)

    def summary(self) -> str:
        """Human-readable summary."""
        lines = []
        for status in ["available", "rate_limited", "paid", "planned"]:
            dims = [d for d in self._dimensions.values() if d.status == status]
            if dims:
                enabled = sum(1 for d in dims if d.enabled)
                lines.append(f"  {status}: {len(dims)} total, {enabled} enabled")
                for d in dims[:3]:
                    lines.append(f"    - {d.key}: {d.label} [{d.source}]")
                if len(dims) > 3:
                    lines.append(f"    ... and {len(dims)-3} more")
        return "\n".join(lines)

    def validate(self) -> List[str]:
        """Return registry contract issues. Empty list means the config is valid."""
        issues: List[str] = []
        for key, dim in self._dimensions.items():
            if dim.source and dim.source not in ALLOWED_SOURCES:
                issues.append(f"{key}: invalid source {dim.source!r}")
            if dim.asset and dim.asset not in ALLOWED_ASSETS:
                issues.append(f"{key}: invalid asset {dim.asset!r}")
            if dim.status not in ALLOWED_STATUSES:
                issues.append(f"{key}: invalid status {dim.status!r}")
            if dim.freq not in ALLOWED_FREQS:
                issues.append(f"{key}: invalid freq {dim.freq!r}")
            if dim.repair_policy not in ALLOWED_REPAIR_POLICIES:
                issues.append(f"{key}: invalid repair_policy {dim.repair_policy!r}")
            if dim.cache:
                path = Path(dim.cache)
                if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                    issues.append(f"{key}: cache must be a relative path inside the DataHub store root")
            elif dim.enabled and dim.status != "planned":
                issues.append(f"{key}: enabled non-planned dimension has no cache path")
            if dim.enabled and dim.health_enabled and not dim.health_table:
                issues.append(f"{key}: enabled health dimension has no health table name")
        return issues

    def health_metadata(self, repairable_tables: Iterable[str] = ()) -> dict[str, HealthTableMeta]:
        """Build DB Health metadata from registry dimensions plus computed/system tables."""
        repairable = set(repairable_tables)
        meta: dict[str, HealthTableMeta] = {}
        for dim in self._dimensions.values():
            if not dim.enabled or not dim.health_enabled:
                continue
            table = dim.health_table or DEFAULT_HEALTH_TABLES.get(dim.key, dim.key)
            meta[table] = HealthTableMeta(
                table=table,
                source=SOURCE_LABELS.get(dim.source, dim.source),
                label_zh=dim.health_label or dim.label,
                repairable=table in repairable and dim.repair_policy != "none",
                registry_key=dim.key,
                freshness_sla_days=dim.freshness_sla_days,
                repair_policy=dim.repair_policy,
                partition_key=dim.partition_key,
            )

        for table, item in COMPUTED_HEALTH_META.items():
            meta[table] = HealthTableMeta(
                table=table,
                source=item.source,
                label_zh=item.label_zh,
                repairable=table in repairable and item.repair_policy != "none",
                registry_key=item.registry_key,
                freshness_sla_days=item.freshness_sla_days,
                repair_policy=item.repair_policy,
                partition_key=item.partition_key,
            )
        return meta

    def __repr__(self) -> str:
        return f"<DataRegistry: {len(self._dimensions)} dimensions>"


# ── Global singleton ──
_registry: Optional[DataRegistry] = None


def get_registry() -> DataRegistry:
    global _registry
    if _registry is None:
        _registry = DataRegistry()
    return _registry


def reset_registry() -> None:
    global _registry
    _registry = None


def is_available(key: str) -> bool:
    reg = get_registry()
    d = reg.get(key)
    return d is not None and d.is_available
