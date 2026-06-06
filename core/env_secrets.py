"""Environment-only secret helpers.

This module deliberately reads only ``os.environ``. Runtime code must not load
API keys from YAML, project files, or user-level ``.env`` files.
"""

from __future__ import annotations

import os
from collections.abc import Iterable


def _names(primary: str, aliases: Iterable[str] = ()) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for name in (primary, *tuple(aliases)):
        clean = str(name or "").strip()
        if clean and clean not in seen:
            ordered.append(clean)
            seen.add(clean)
    return ordered


def mask_secret(value: str) -> str:
    """Return a stable redacted display value without leaking the secret."""
    clean = str(value or "").strip()
    if not clean:
        return ""
    if len(clean) <= 8:
        return "****"
    return f"{clean[:4]}****{clean[-4:]}"


def read_env_secret(primary: str, aliases: Iterable[str] = ()) -> str:
    """Read a secret from process environment only."""
    for name in _names(primary, aliases):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def secret_status(primary: str, aliases: Iterable[str] = ()) -> dict[str, object]:
    """Return masked status for a secret without exposing its raw value."""
    names = _names(primary, aliases)
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return {
                "name": primary,
                "aliases": [n for n in names if n != primary],
                "status": "ok",
                "source": name,
                "masked": mask_secret(value),
            }
    return {
        "name": primary,
        "aliases": [n for n in names if n != primary],
        "status": "missing",
        "source": "",
        "masked": "",
    }
