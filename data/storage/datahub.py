"""
DataHub — centralized data storage facade.

The project deliberately keeps Parquet as the durable store and DuckDB as the
query engine. DataHub is the stable facade: one public entry point for paths,
atomic Parquet writes, append semantics, latest-batch reads, dimensions,
manifest metadata, and lightweight storage auditing.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import pandas as pd

from core.settings import get_section
from data.storage.datahub_dimensions import DimensionStore
from data.storage.datahub_manifest import ManifestStore
from data.storage.datahub_parquet import ParquetStore
from data.storage.datahub_paths import DataHubPaths, PROJECT_ROOT, resolve_path


@dataclass(frozen=True)
class DatasetSpec:
    """A known logical dataset in the local store."""

    key: str
    path: Path
    kind: str
    owner: str
    description: str = ""


class DataHub:
    """Unified local data hub for the Open Quant Company repository."""

    def __init__(
        self,
        runtime_root: str | os.PathLike | None = None,
        store_root: str | os.PathLike | None = None,
        cache_root: str | os.PathLike | None = None,
        artifact_root: str | os.PathLike | None = None,
        db_root: str | os.PathLike | None = None,
        project_root: str | os.PathLike | None = None,
        create: bool = True,
    ):
        project = resolve_path(project_root or PROJECT_ROOT)
        path_cfg = get_section("paths", {}) or {}
        env_var_root = os.environ.get("ASTROLABE_VAR", "").strip()

        runtime_default = runtime_root or env_var_root or path_cfg.get("runtime_root") or project / "var"
        runtime_path = Path(runtime_default)
        use_runtime_layout = bool(env_var_root and runtime_root is None)
        store_default = store_root or (runtime_path / "store" if use_runtime_layout else path_cfg.get("store_root")) or runtime_path / "store"
        cache_default = cache_root or (runtime_path / "cache" if use_runtime_layout else path_cfg.get("cache_root")) or runtime_path / "cache"
        artifact_default = (
            artifact_root
            or (runtime_path / "artifacts" if use_runtime_layout else path_cfg.get("artifact_root"))
            or runtime_path / "artifacts"
        )
        db_default = db_root or (runtime_path / "db" if use_runtime_layout else path_cfg.get("db_root")) or runtime_path / "db"

        self.paths = DataHubPaths(project, runtime_default, store_default, cache_default, artifact_default, db_default)
        self.project_root = self.paths.project_root
        self.store_root = self.paths.store_root
        self.cache_root = self.paths.cache_root

        self.manifest = ManifestStore(self.paths)
        self.parquet = ParquetStore(self.paths, self.manifest)
        self.dimensions = DimensionStore(self.paths, self.parquet.list_parquet)

        if create:
            self.ensure_layout()

    @property
    def project_root(self) -> Path:
        return self.paths.project_root

    @project_root.setter
    def project_root(self, value: str | os.PathLike) -> None:
        self.paths.project_root = resolve_path(value)

    @property
    def store_root(self) -> Path:
        return self.paths.store_root

    @store_root.setter
    def store_root(self, value: str | os.PathLike) -> None:
        self.paths.store_root = resolve_path(value, self.paths.project_root)

    @property
    def cache_root(self) -> Path:
        return self.paths.cache_root

    @cache_root.setter
    def cache_root(self, value: str | os.PathLike) -> None:
        self.paths.cache_root = resolve_path(value, self.paths.project_root)

    # ── Directory layout ─────────────────────────────────────

    def ensure_layout(self) -> None:
        self.paths.ensure_layout()

    def resolve_path(self, path: str | os.PathLike, base: Path | None = None) -> Path:
        return self.paths.resolve_path(path, base)

    def store_path(self, asset_type: str | None = None) -> Path:
        return self.paths.store_path(asset_type)

    def store_dir(self, asset_type: str | None = None) -> Path:
        return self.paths.store_dir(asset_type)

    def runtime_dir(self) -> Path:
        return self.paths.runtime_dir()

    def artifact_dir(self, kind: str | None = None) -> Path:
        return self.paths.artifact_dir(kind)

    def artifact_path(self, kind: str, name: str) -> Path:
        return self.paths.artifact_path(kind, name)

    def db_path(self, name: str) -> Path:
        return self.paths.db_path(name)

    def stock_data_dir(self, name: str) -> Path:
        return self.paths.stock_data_dir(name)

    def signals_dir(self) -> Path:
        return self.paths.signals_dir()

    def signals_prev_dir(self) -> Path:
        return self.paths.signals_prev_dir()

    def signal_path(self, strategy: str) -> Path:
        return self.paths.signal_path(strategy)

    def signal_prev_path(self, strategy: str) -> Path:
        return self.paths.signal_prev_path(strategy)

    def buffett_scan_path(self) -> Path:
        return self.paths.buffett_scan_path()

    def scan_meta_path(self) -> Path:
        return self.paths.scan_meta_path()

    def features_dir(self) -> Path:
        return self.paths.features_dir()

    def feature_path(self, as_of_key: str) -> Path:
        return self.paths.feature_path(as_of_key)

    def paper_dir(self) -> Path:
        return self.paths.paper_dir()

    def paper_path(self, name: str) -> Path:
        return self.paths.paper_path(name)

    def macro_path(self, name: str) -> Path:
        return self.paths.macro_path(name)

    def asset_daily_path(self, asset_type: str, symbol: str) -> Path:
        return self.paths.asset_daily_path(asset_type, symbol)

    def stock_daily_path(self, symbol: str) -> Path:
        return self.paths.stock_daily_path(symbol)

    def stock_daily_raw_path(self, symbol: str) -> Path:
        return self.paths.stock_daily_raw_path(symbol)

    def stock_daily_hfq_path(self, symbol: str) -> Path:
        return self.paths.stock_daily_hfq_path(symbol)

    def stock_adj_factor_path(self, symbol: str) -> Path:
        return self.paths.stock_adj_factor_path(symbol)

    def stock_corporate_actions_path(self, symbol: str) -> Path:
        return self.paths.stock_corporate_actions_path(symbol)

    def stock_financial_path(self, symbol: str) -> Path:
        return self.paths.stock_financial_path(symbol)

    def stock_fina_indicator_path(self, symbol: str) -> Path:
        return self.paths.stock_fina_indicator_path(symbol)

    def stock_valuation_path(self, symbol: str) -> Path:
        return self.paths.stock_valuation_path(symbol)

    def model_path(self, name: str) -> Path:
        return self.paths.model_path(name)

    def system_monitor_path(self) -> Path:
        return self.paths.system_monitor_path()

    def token_usage_path(self) -> Path:
        return self.paths.token_usage_path()

    def llm_usage_path(self) -> Path:
        return self.paths.llm_usage_path()

    def llm_project_usage_path(self) -> Path:
        return self.paths.llm_project_usage_path()

    def manifest_dir(self) -> Path:
        return self.paths.manifest_dir()

    def manifest_path(self) -> Path:
        return self.paths.manifest_path()

    # ── Registry-backed dimension paths ─────────────────────

    def dimension_root(self, key: str) -> Path:
        """Return the stable root directory/file prefix for a data_registry dimension."""
        return self.dimensions.dimension_root(key)

    def dimension_path(self, key: str, **values: Any) -> Path:
        """Expand a data_registry cache pattern into a concrete path."""
        return self.dimensions.dimension_path(key, **values)

    def list_dimension_snapshots(self, key: str, pattern: str = "*.parquet") -> list[Path]:
        """Return sorted parquet snapshots for a registry-backed dimension."""
        return self.dimensions.list_dimension_snapshots(key, pattern)

    def latest_dimension_snapshot(self, key: str, pattern: str = "*.parquet") -> Path | None:
        """Return the latest parquet snapshot for a registry-backed dimension."""
        return self.dimensions.latest_dimension_snapshot(key, pattern)

    # ── Parquet helpers ──────────────────────────────────────

    def read_parquet(
        self,
        path: str | os.PathLike,
        default: Optional[pd.DataFrame] = None,
        columns: Optional[Sequence[str]] = None,
    ) -> Optional[pd.DataFrame]:
        return self.parquet.read(path, default=default, columns=columns)

    def write_parquet(
        self,
        df: pd.DataFrame,
        path: str | os.PathLike,
        index: bool = False,
        *,
        producer: str | None = None,
        record_manifest: bool = True,
    ) -> Path:
        return self.parquet.write(df, path, index=index, producer=producer, record_manifest=record_manifest)

    def append_parquet(
        self,
        path: str | os.PathLike,
        rows: pd.DataFrame | list[dict] | dict,
        dedupe_subset: Iterable[str] | None = None,
        sort_by: Iterable[str] | None = None,
    ) -> Path:
        return self.parquet.append(path, rows, dedupe_subset=dedupe_subset, sort_by=sort_by)

    def latest_batch(self, path: str | os.PathLike, ts_col: str = "computed_at") -> pd.DataFrame:
        return self.parquet.latest_batch(path, ts_col=ts_col)

    def list_parquet(self, directory: str | os.PathLike, pattern: str = "*.parquet") -> list[Path]:
        return self.parquet.list_parquet(directory, pattern)

    # ── Manifest helpers ────────────────────────────────────

    def read_manifest(self) -> pd.DataFrame:
        return self.manifest.read()

    def manifest_for(self, path: str | os.PathLike) -> dict[str, Any]:
        return self.manifest.for_path(path)

    def _is_manifest_path(self, target: Path) -> bool:
        return self.manifest.is_manifest_path(target)

    def _relative_to_project(self, target: Path) -> str:
        return self.manifest.relative_to_project(target)

    def _schema_hash(self, df: pd.DataFrame) -> str:
        return self.manifest.schema_hash(df)

    def _file_sha256(self, path: Path) -> str:
        return self.manifest.file_sha256(path)

    def _date_range(self, df: pd.DataFrame) -> tuple[str, str, str]:
        return self.manifest.date_range(df)

    def _record_manifest(self, target: Path, df: pd.DataFrame, producer: str | None = None) -> None:
        self.manifest.record(target, df, producer=producer)

    # ── JSON helpers ────────────────────────────────────────

    def read_json(self, path: str | os.PathLike, default: Any = None) -> Any:
        target = self.resolve_path(path)
        if not target.exists():
            return default
        try:
            with open(target, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def write_json(self, data: Any, path: str | os.PathLike, *, indent: int | None = None) -> Path:
        target = self.resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".tmp-{uuid.uuid4().hex}-{target.name}")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        return target

    # ── Catalog / audit ─────────────────────────────────────

    def catalog(self) -> dict[str, DatasetSpec]:
        catalog = {
            "signals": DatasetSpec("signals", self.signals_dir(), "directory", "strategies", "Latest strategy signals"),
            "signals_prev": DatasetSpec("signals_prev", self.signals_prev_dir(), "directory", "strategies", "Previous signal snapshots"),
            "scan_meta": DatasetSpec("scan_meta", self.scan_meta_path(), "parquet", "strategies", "Strategy scan metadata"),
            "features": DatasetSpec("features", self.features_dir(), "partitioned_parquet", "research", "Monthly PIT feature slices"),
            "paper": DatasetSpec("paper", self.paper_dir(), "directory", "broker", "Paper-trading state, NAV and trades"),
            "macro": DatasetSpec("macro", self.store_path("macro"), "directory", "macro", "Macro and rates datasets"),
            "manifest": DatasetSpec("manifest", self.manifest_path(), "parquet", "datahub", "DataHub parquet write manifest"),
            "system_monitor": DatasetSpec("system_monitor", self.system_monitor_path(), "sqlite", "system", "System metrics time-series DB"),
            "token_usage": DatasetSpec("token_usage", self.token_usage_path(), "json", "system", "LLM token usage cache"),
            "llm_usage": DatasetSpec("llm_usage", self.llm_project_usage_path(), "parquet", "system", "Generic LLM provider response usage ledger"),
        }
        try:
            from data.storage.dimensions import get_registry

            for dim in get_registry().all.values():
                if not dim.cache:
                    continue
                root = self._registry_cache_root(dim.cache)
                catalog[f"dimension:{dim.key}"] = DatasetSpec(
                    key=f"dimension:{dim.key}",
                    path=root,
                    kind="registry_dataset",
                    owner=dim.source or dim.asset,
                    description=f"{dim.label} [{dim.freq}/{dim.status}]",
                )
        except Exception:
            pass
        return catalog

    def _registry_cache_root(self, pattern: str) -> Path:
        return self.paths.registry_cache_root(pattern)

    def audit(self, include_rows: bool = False) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for spec in self.catalog().values():
            item: dict[str, Any] = {
                "key": spec.key,
                "kind": spec.kind,
                "owner": spec.owner,
                "path": str(spec.path),
                "exists": spec.path.exists(),
                "description": spec.description,
            }
            if spec.path.is_dir():
                files = self.list_parquet(spec.path)
                item["parquet_files"] = len(files)
                item["bytes"] = sum(p.stat().st_size for p in files if p.exists())
            elif spec.path.exists():
                item["bytes"] = spec.path.stat().st_size
                manifest = self.manifest_for(spec.path)
                if manifest:
                    item["manifest"] = manifest
                if include_rows and spec.kind == "parquet":
                    try:
                        item["rows"] = len(pd.read_parquet(spec.path))
                    except Exception:
                        item["rows"] = None
            items.append(item)
        return items


_DEFAULT_HUB: DataHub | None = None
_DEFAULT_HUB_SIGNATURE: tuple[str] | None = None


def _default_hub_signature() -> tuple[str]:
    return (os.environ.get("ASTROLABE_VAR", ""),)


def get_datahub() -> DataHub:
    global _DEFAULT_HUB, _DEFAULT_HUB_SIGNATURE
    signature = _default_hub_signature()
    if _DEFAULT_HUB is None or _DEFAULT_HUB_SIGNATURE != signature:
        _DEFAULT_HUB = DataHub()
        _DEFAULT_HUB_SIGNATURE = signature
    return _DEFAULT_HUB


def reset_datahub() -> None:
    global _DEFAULT_HUB, _DEFAULT_HUB_SIGNATURE
    _DEFAULT_HUB = None
    _DEFAULT_HUB_SIGNATURE = None
