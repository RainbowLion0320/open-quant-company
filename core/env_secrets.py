"""Environment-only secret helpers.

This module deliberately reads only ``os.environ``. Runtime code must not load
API keys from YAML, project files, or user-level ``.env`` files.
"""

from __future__ import annotations

import os


def mask_secret(value: str) -> str:
    """Return a stable redacted display value without leaking the secret."""
    clean = str(value or "").strip()
    if not clean:
        return ""
    if len(clean) <= 8:
        return "****"
    return f"{clean[:4]}****{clean[-4:]}"


def read_env_secret(name: str) -> str:
    """Read a secret from process environment only."""
    clean = str(name or "").strip()
    if not clean:
        return ""
    return os.environ.get(clean, "").strip()


def secret_status(name: str) -> dict[str, object]:
    """Return masked status for a secret without exposing its raw value."""
    clean = str(name or "").strip()
    value = os.environ.get(clean, "").strip() if clean else ""
    if value:
        return {
            "name": clean,
            "status": "ok",
            "source": clean,
            "masked": mask_secret(value),
        }
    return {
        "name": clean,
        "status": "missing",
        "source": "",
        "masked": "",
    }
