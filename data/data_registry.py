"""
Data Dimension Registry — 统一数据维度管理

Like StrategyRegistry: single source of truth for what data exists.
配置: config/settings.yaml → data_registry

用法:
  from data.data_registry import get_registry, is_available
  reg = get_registry()
  dims = reg.get_enabled()  # 所有已启用的维度
  reg.get("holder_number")  # 单个维度详情
"""
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass


ALLOWED_SOURCES = {"akshare", "tushare_free", "tushare_paid", "future", "computed", "system"}
ALLOWED_ASSETS = {"stock", "macro", "fund", "futures", "crypto", "bond", "system"}
ALLOWED_STATUSES = {"available", "rate_limited", "paid", "planned"}
ALLOWED_FREQS = {"daily", "monthly", "quarterly", "event", "minute", "intraday", "system"}


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
        cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
        with open(cfg_path) as f:
            cfg = yaml.safe_load(f)

        for key, info in cfg.get("data_registry", {}).items():
            self._dimensions[key] = DataDimension(
                key=key,
                source=info.get("source", ""),
                asset=info.get("asset", ""),
                status=info.get("status", "planned"),
                freq=info.get("freq", "daily"),
                enabled=info.get("enabled", False),
                label=info.get("label", key),
                cache=info.get("cache", ""),
                description=info.get("description", ""),
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
            if dim.cache:
                path = Path(dim.cache)
                if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                    issues.append(f"{key}: cache must be a relative path inside data/store")
            elif dim.enabled and dim.status != "planned":
                issues.append(f"{key}: enabled non-planned dimension has no cache path")
        return issues

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
