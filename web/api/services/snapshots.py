"""Snapshot discovery helpers for registry-backed datasets."""

from __future__ import annotations

from pathlib import Path


def latest_snapshot(
    *,
    registry_root: Path | None,
    legacy_root: Path | None,
    legacy_prefix: str,
) -> Path | None:
    """Find the latest registry snapshot, with legacy flat-file fallback."""
    if registry_root and registry_root.exists():
        registry_candidates = sorted(registry_root.glob("*.parquet"), reverse=True)
        if registry_candidates:
            return registry_candidates[0]

    if legacy_root and legacy_root.exists():
        legacy_candidates = sorted(legacy_root.glob(f"{legacy_prefix}*.parquet"), reverse=True)
        if legacy_candidates:
            return legacy_candidates[0]

    return None


def latest_hub_snapshot(hub, dimension: str, legacy_root: Path, legacy_prefix: str) -> Path | None:
    """Resolve a DataHub registry dimension snapshot with legacy fallback."""
    registry_root: Path | None = None
    try:
        registry_root = hub.dimension_root(dimension)
    except Exception:
        registry_root = None
    return latest_snapshot(registry_root=registry_root, legacy_root=legacy_root, legacy_prefix=legacy_prefix)
