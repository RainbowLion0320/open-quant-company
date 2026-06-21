from __future__ import annotations

import math
from typing import Any


def coerce_float(value: Any, default: float = 0.0) -> float:
    parsed, error = parse_optional_float(value)
    return default if error else parsed


def coerce_int(value: Any, default: int = 0) -> int:
    parsed, error = parse_optional_int(value)
    return default if error else parsed


def parse_required_float(value: Any, *, missing: str, invalid: str) -> tuple[float, str]:
    if _missing(value):
        return 0.0, missing
    parsed, error = parse_optional_float(value)
    return parsed, invalid if error else ""


def parse_required_int(value: Any, *, missing: str, invalid: str) -> tuple[int, str]:
    if _missing(value):
        return 0, missing
    parsed, error = parse_optional_int(value)
    return parsed, invalid if error else ""


def parse_optional_float(value: Any) -> tuple[float, str]:
    if isinstance(value, bool):
        return 0.0, "invalid_float"
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0, "invalid_float"
    if not math.isfinite(parsed):
        return 0.0, "invalid_float"
    return parsed, ""


def parse_optional_int(value: Any) -> tuple[int, str]:
    if isinstance(value, bool):
        return 0, "invalid_int"
    try:
        parsed_float = float(value)
    except (TypeError, ValueError):
        return 0, "invalid_int"
    if not math.isfinite(parsed_float) or not parsed_float.is_integer():
        return 0, "invalid_int"
    return int(parsed_float), ""


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False
