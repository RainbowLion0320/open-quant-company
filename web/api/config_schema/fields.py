"""Field helpers for config center schemas."""

from __future__ import annotations

from typing import Any


def field(
    key: str,
    label: str,
    typ: str = "float",
    *,
    description: str = "",
    min_val: Any = None,
    max_val: Any = None,
    default: Any = None,
    options: list | None = None,
) -> dict[str, Any]:
    descriptor: dict[str, Any] = {"key": key, "label": label, "type": typ}
    if description:
        descriptor["description"] = description
    if min_val is not None:
        descriptor["min"] = min_val
    if max_val is not None:
        descriptor["max"] = max_val
    if default is not None:
        descriptor["default"] = default
    if options is not None:
        descriptor["options"] = options
    return descriptor
