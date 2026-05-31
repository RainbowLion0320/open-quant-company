"""Parquet read/write helpers used by DataHub."""

from __future__ import annotations

import fcntl
import os
import uuid
from pathlib import Path
from typing import Iterable, Optional, Sequence

import pandas as pd

from data.datahub_manifest import ManifestStore
from data.datahub_paths import DataHubPaths


class ParquetStore:
    """Atomic parquet IO with optional manifest recording."""

    def __init__(self, paths: DataHubPaths, manifest: ManifestStore):
        self.paths = paths
        self.manifest = manifest

    def read(
        self,
        path: str | os.PathLike,
        default: Optional[pd.DataFrame] = None,
        columns: Optional[Sequence[str]] = None,
    ) -> Optional[pd.DataFrame]:
        target = self.paths.resolve_path(path)
        if not target.exists():
            return default
        try:
            return pd.read_parquet(target, columns=columns)
        except Exception:
            if default is not None:
                return default
            raise

    def write(
        self,
        df: pd.DataFrame,
        path: str | os.PathLike,
        index: bool = False,
        *,
        producer: str | None = None,
        record_manifest: bool = True,
    ) -> Path:
        target = self.paths.resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".tmp-{uuid.uuid4().hex}-{target.name}")
        try:
            df.to_parquet(tmp, index=index)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        if record_manifest and not self.manifest.is_manifest_path(target):
            self.manifest.record(target, df, producer=producer)
        return target

    def append(
        self,
        path: str | os.PathLike,
        rows: pd.DataFrame | list[dict] | dict,
        dedupe_subset: Iterable[str] | None = None,
        sort_by: Iterable[str] | None = None,
    ) -> Path:
        target = self.paths.resolve_path(path)
        if isinstance(rows, pd.DataFrame):
            new_df = rows.copy()
        elif isinstance(rows, dict):
            new_df = pd.DataFrame([rows])
        else:
            new_df = pd.DataFrame(list(rows))

        lock_path = target.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                existing = self.read(target, default=pd.DataFrame())
                merged = pd.concat([existing, new_df], ignore_index=True) if existing is not None and len(existing) else new_df

                if dedupe_subset:
                    subset = [c for c in dedupe_subset if c in merged.columns]
                    if subset:
                        merged = merged.drop_duplicates(subset=subset, keep="last")
                if sort_by:
                    cols = [c for c in sort_by if c in merged.columns]
                    if cols:
                        merged = merged.sort_values(cols)

                result = self.write(merged, target)
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
        return result

    def latest_batch(self, path: str | os.PathLike, ts_col: str = "computed_at") -> pd.DataFrame:
        df = self.read(path, default=pd.DataFrame())
        if df is None or df.empty or ts_col not in df.columns:
            return pd.DataFrame() if df is None else df
        valid = df[ts_col].dropna()
        if valid.empty:
            return df
        latest = valid.max()
        return df[df[ts_col] == latest].copy()

    def list_parquet(self, directory: str | os.PathLike, pattern: str = "*.parquet") -> list[Path]:
        path = self.paths.resolve_path(directory)
        if not path.exists():
            return []
        return sorted(path.glob(pattern))
