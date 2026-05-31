"""Manifest metadata store for DataHub parquet writes."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from data.datahub_paths import DataHubPaths, env_first


DATE_COLUMNS = ("date", "trade_date", "ann_date", "end_date", "ts", "quarter", "utc_date", "month")


class ManifestStore:
    """Read and update DataHub manifest metadata."""

    def __init__(self, paths: DataHubPaths):
        self.paths = paths

    def read(self) -> pd.DataFrame:
        manifest_path = self.paths.manifest_path()
        if not manifest_path.exists():
            return pd.DataFrame()
        try:
            return pd.read_parquet(manifest_path)
        except Exception:
            return pd.DataFrame()

    def for_path(self, path: str | os.PathLike) -> dict[str, Any]:
        target = self.paths.resolve_path(path)
        rel = self.relative_to_project(target)
        manifest = self.read()
        if manifest.empty or "path" not in manifest.columns:
            return {}
        rows = manifest[manifest["path"] == rel]
        if rows.empty:
            return {}
        return rows.iloc[-1].to_dict()

    def is_manifest_path(self, target: Path) -> bool:
        try:
            target.relative_to(self.paths.manifest_dir())
            return True
        except ValueError:
            return False

    def relative_to_project(self, target: Path) -> str:
        try:
            return str(target.relative_to(self.paths.project_root))
        except ValueError:
            return str(target)

    def schema_hash(self, df: pd.DataFrame) -> str:
        schema = "|".join(f"{col}:{df[col].dtype}" for col in df.columns)
        return hashlib.sha256(schema.encode("utf-8")).hexdigest()[:16]

    def file_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def date_range(self, df: pd.DataFrame) -> tuple[str, str, str]:
        for col in df.columns:
            if str(col).lower() not in DATE_COLUMNS:
                continue
            try:
                series = pd.to_datetime(df[col], errors="coerce").dropna()
            except Exception:
                continue
            if not series.empty:
                return col, series.min().date().isoformat(), series.max().date().isoformat()
        return "", "", ""

    def record(self, target: Path, df: pd.DataFrame, producer: str | None = None) -> None:
        try:
            date_col, date_min, date_max = self.date_range(df)
            record = {
                "path": self.relative_to_project(target),
                "producer": producer or env_first("ASTROLABE_PRODUCER"),
                "row_count": int(len(df)),
                "column_count": int(len(df.columns)),
                "date_column": date_col,
                "date_min": date_min,
                "date_max": date_max,
                "schema_hash": self.schema_hash(df),
                "file_sha256": self.file_sha256(target),
                "size_bytes": int(target.stat().st_size),
                "updated_at": datetime.now().isoformat(),
            }
            manifest_path = self.paths.manifest_path()
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            existing = pd.read_parquet(manifest_path) if manifest_path.exists() else pd.DataFrame()
            next_df = pd.DataFrame([record])
            if not existing.empty and "path" in existing.columns:
                existing = existing[existing["path"] != record["path"]]
                next_df = pd.concat([existing, next_df], ignore_index=True)
            tmp = manifest_path.with_name(f".tmp-{uuid.uuid4().hex}-{manifest_path.name}")
            try:
                next_df.sort_values("path").to_parquet(tmp, index=False)
                os.replace(tmp, manifest_path)
            finally:
                tmp.unlink(missing_ok=True)
        except Exception:
            return
