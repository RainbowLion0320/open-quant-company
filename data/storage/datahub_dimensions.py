"""DataRegistry-backed dimension path helpers for DataHub."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from data.storage.datahub_paths import DataHubPaths


class DimensionStore:
    """Resolve and discover DataRegistry-backed physical cache paths."""

    def __init__(self, paths: DataHubPaths, list_parquet: Callable[[str | Path, str], list[Path]]):
        self.paths = paths
        self._list_parquet = list_parquet

    def dimension_root(self, key: str) -> Path:
        from data.storage.dimensions import get_registry

        dim = get_registry().get(key)
        if dim is None or not dim.cache:
            raise KeyError(f"Unknown or uncached data dimension: {key}")
        return self.paths.registry_cache_root(dim.cache)

    def dimension_path(self, key: str, **values: Any) -> Path:
        from data.storage.dimensions import get_registry

        dim = get_registry().get(key)
        if dim is None or not dim.cache:
            raise KeyError(f"Unknown or uncached data dimension: {key}")
        return self.paths.expand_registry_cache(key, dim.cache, values)

    def list_dimension_snapshots(self, key: str, pattern: str = "*.parquet") -> list[Path]:
        try:
            root = self.dimension_root(key)
        except Exception:
            return []
        if root.is_file():
            return [root]
        if not root.exists():
            return []
        return self._list_parquet(root, pattern)

    def latest_dimension_snapshot(self, key: str, pattern: str = "*.parquet") -> Path | None:
        candidates = self.list_dimension_snapshots(key, pattern)
        return candidates[-1] if candidates else None
