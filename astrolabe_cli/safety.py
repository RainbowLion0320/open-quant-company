from __future__ import annotations

from typing import Any


VALID_RUNTIME_MODES = {"production", "research"}


def validate_runtime_mode(mode: str) -> str:
    if mode not in VALID_RUNTIME_MODES:
        raise ValueError(f"Invalid runtime mode: {mode}. Expected production or research.")
    return mode


def dry_run_payload(action: str, **kwargs: Any) -> dict[str, Any]:
    return {
        "dry_run": True,
        "action": action,
        "would_run": kwargs,
    }
