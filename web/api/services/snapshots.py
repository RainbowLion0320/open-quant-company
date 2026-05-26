"""Snapshot discovery helpers for registry-backed datasets."""

from __future__ import annotations

from pathlib import Path


def latest_snapshot(
    *,
    registry_root: Path | None,
) -> Path | None:
    """Find the latest registry snapshot."""
    if registry_root and registry_root.exists():
        registry_candidates = sorted(registry_root.glob("*.parquet"), reverse=True)
        if registry_candidates:
            return registry_candidates[0]

    return None


def latest_hub_snapshot(hub, dimension: str) -> Path | None:
    """Resolve a DataHub registry dimension snapshot."""
    registry_root: Path | None = None
    try:
        registry_root = hub.dimension_root(dimension)
    except Exception:
        registry_root = None
    return latest_snapshot(registry_root=registry_root)
