"""
DataHub — centralized data storage facade.

The project deliberately keeps Parquet as the durable store and DuckDB as the
query engine.  DataHub is the missing middle layer: one place for paths,
atomic Parquet writes, append semantics, latest-batch reads and lightweight
storage auditing.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_path(path: str | os.PathLike, base: Path = PROJECT_ROOT) -> Path:
    raw = os.path.expandvars(os.path.expanduser(str(path)))
    resolved = Path(raw)
    if not resolved.is_absolute():
        resolved = base / resolved
    return resolved.resolve()


def _safe_leaf(value: str, label: str = "name") -> str:
    text = str(value).strip()
    if not text or "/" in text or "\\" in text or text in {".", ".."}:
        raise ValueError(f"Invalid {label}: {value!r}")
    return text


@dataclass(frozen=True)
class DatasetSpec:
    """A known logical dataset in the local store."""

    key: str
    path: Path
    kind: str
    owner: str
    description: str = ""


class DataHub:
    """Unified local data hub for the quant-agent repository."""

    def __init__(
        self,
        store_root: str | os.PathLike | None = None,
        cache_root: str | os.PathLike | None = None,
        project_root: str | os.PathLike | None = None,
        create: bool = True,
    ):
        self.project_root = _resolve_path(project_root or PROJECT_ROOT)
        store_default = os.environ.get("QUANT_AGENT_STORE") or self.project_root / "data" / "store"
        cache_default = os.environ.get("QUANT_AGENT_CACHE") or self.project_root / "data" / "cache"
        self.store_root = _resolve_path(store_root or store_default, self.project_root)
        self.cache_root = _resolve_path(cache_root or cache_default, self.project_root)
        if create:
            self.ensure_layout()

    # ── Directory layout ─────────────────────────────────────

    def ensure_layout(self) -> None:
        for path in [
            self.store_root,
            self.cache_root,
            self.signals_dir(),
            self.signals_prev_dir(),
            self.features_dir(),
            self.paper_dir(),
            self.store_dir("stock"),
            self.store_dir("macro"),
            self.store_dir("financials"),
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def resolve_path(self, path: str | os.PathLike, base: Path | None = None) -> Path:
        return _resolve_path(path, base or self.project_root)

    def store_dir(self, asset_type: str | None = None) -> Path:
        if asset_type is None:
            return self.store_root
        path = self.store_root / _safe_leaf(asset_type, "asset_type")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cache_dir(self) -> Path:
        self.cache_root.mkdir(parents=True, exist_ok=True)
        return self.cache_root

    def signals_dir(self) -> Path:
        return self.store_root / "signals"

    def signals_prev_dir(self) -> Path:
        return self.store_root / "signals_prev"

    def signal_path(self, strategy: str) -> Path:
        return self.signals_dir() / f"{_safe_leaf(strategy, 'strategy')}.parquet"

    def signal_prev_path(self, strategy: str) -> Path:
        return self.signals_prev_dir() / f"{_safe_leaf(strategy, 'strategy')}.parquet"

    def buffett_scan_path(self) -> Path:
        return self.signals_dir() / "buffett_scan.parquet"

    def scan_meta_path(self) -> Path:
        return self.store_root / "scan_meta.parquet"

    def features_dir(self) -> Path:
        return self.store_root / "features"

    def feature_path(self, month: str) -> Path:
        return self.features_dir() / f"{_safe_leaf(month, 'month')}.parquet"

    def paper_dir(self) -> Path:
        return self.store_root / "paper"

    def paper_path(self, name: str) -> Path:
        return self.paper_dir() / f"{_safe_leaf(name, 'paper dataset')}.parquet"

    def macro_path(self, name: str) -> Path:
        return self.store_dir("macro") / f"{_safe_leaf(name, 'macro dataset')}.parquet"

    def asset_daily_path(self, asset_type: str, symbol: str) -> Path:
        return self.store_dir(asset_type) / "daily" / f"{_safe_leaf(symbol, 'symbol')}.parquet"

    def model_path(self, name: str) -> Path:
        return self.project_root / "data" / "models" / f"{_safe_leaf(name, 'model dataset')}.parquet"

    def system_monitor_path(self) -> Path:
        return self.store_root / "system_monitor.db"

    def token_usage_path(self) -> Path:
        return self.cache_root / "token_usage.json"

    def llm_usage_path(self) -> Path:
        return self.cache_root / "llm_usage_today.json"

    def hindsight_tokens_path(self) -> Path:
        return self.cache_root / "hindsight_tokens.json"

    # ── Parquet helpers ──────────────────────────────────────

    def read_parquet(
        self,
        path: str | os.PathLike,
        default: Optional[pd.DataFrame] = None,
        columns: Optional[Sequence[str]] = None,
    ) -> Optional[pd.DataFrame]:
        target = self.resolve_path(path)
        if not target.exists():
            return default
        try:
            return pd.read_parquet(target, columns=columns)
        except Exception:
            if default is not None:
                return default
            raise

    def write_parquet(self, df: pd.DataFrame, path: str | os.PathLike, index: bool = False) -> Path:
        target = self.resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".tmp-{uuid.uuid4().hex}-{target.name}")
        try:
            df.to_parquet(tmp, index=index)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        return target

    def append_parquet(
        self,
        path: str | os.PathLike,
        rows: pd.DataFrame | list[dict] | dict,
        dedupe_subset: Iterable[str] | None = None,
        sort_by: Iterable[str] | None = None,
    ) -> Path:
        target = self.resolve_path(path)
        if isinstance(rows, pd.DataFrame):
            new_df = rows.copy()
        elif isinstance(rows, dict):
            new_df = pd.DataFrame([rows])
        else:
            new_df = pd.DataFrame(list(rows))

        existing = self.read_parquet(target, default=pd.DataFrame())
        merged = pd.concat([existing, new_df], ignore_index=True) if existing is not None and len(existing) else new_df

        if dedupe_subset:
            subset = [c for c in dedupe_subset if c in merged.columns]
            if subset:
                merged = merged.drop_duplicates(subset=subset, keep="last")
        if sort_by:
            cols = [c for c in sort_by if c in merged.columns]
            if cols:
                merged = merged.sort_values(cols)

        return self.write_parquet(merged, target)

    def latest_batch(self, path: str | os.PathLike, ts_col: str = "computed_at") -> pd.DataFrame:
        df = self.read_parquet(path, default=pd.DataFrame())
        if df is None or df.empty or ts_col not in df.columns:
            return pd.DataFrame() if df is None else df
        valid = df[ts_col].dropna()
        if valid.empty:
            return df
        latest = valid.max()
        return df[df[ts_col] == latest].copy()

    def list_parquet(self, directory: str | os.PathLike, pattern: str = "*.parquet") -> list[Path]:
        path = self.resolve_path(directory)
        if not path.exists():
            return []
        return sorted(path.glob(pattern))

    # ── JSON helpers ────────────────────────────────────────

    def read_json(self, path: str | os.PathLike, default: Any = None) -> Any:
        target = self.resolve_path(path)
        if not target.exists():
            return default
        try:
            with open(target) as f:
                return json.load(f)
        except Exception:
            return default

    def write_json(self, data: Any, path: str | os.PathLike, *, indent: int | None = None) -> Path:
        target = self.resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".tmp-{uuid.uuid4().hex}-{target.name}")
        try:
            with open(tmp, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        return target

    # ── Catalog / audit ─────────────────────────────────────

    def catalog(self) -> dict[str, DatasetSpec]:
        return {
            "signals": DatasetSpec("signals", self.signals_dir(), "directory", "strategies", "Latest strategy signals"),
            "signals_prev": DatasetSpec("signals_prev", self.signals_prev_dir(), "directory", "strategies", "Previous signal snapshots"),
            "scan_meta": DatasetSpec("scan_meta", self.scan_meta_path(), "parquet", "strategies", "Strategy scan metadata"),
            "features": DatasetSpec("features", self.features_dir(), "partitioned_parquet", "research", "Monthly PIT feature slices"),
            "paper": DatasetSpec("paper", self.paper_dir(), "directory", "broker", "Paper-trading state, NAV and trades"),
            "macro": DatasetSpec("macro", self.store_dir("macro"), "directory", "macro", "Macro and rates datasets"),
            "system_monitor": DatasetSpec("system_monitor", self.system_monitor_path(), "sqlite", "system", "System metrics time-series DB"),
            "token_usage": DatasetSpec("token_usage", self.token_usage_path(), "json", "system", "LLM token usage cache"),
        }

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
                if include_rows and spec.kind == "parquet":
                    try:
                        item["rows"] = len(pd.read_parquet(spec.path))
                    except Exception:
                        item["rows"] = None
            items.append(item)
        return items


_DEFAULT_HUB: DataHub | None = None


def get_datahub() -> DataHub:
    global _DEFAULT_HUB
    if _DEFAULT_HUB is None:
        _DEFAULT_HUB = DataHub()
    return _DEFAULT_HUB


def reset_datahub() -> None:
    global _DEFAULT_HUB
    _DEFAULT_HUB = None
