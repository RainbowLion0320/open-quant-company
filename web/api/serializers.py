"""Shared API serialization helpers."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd


def json_map(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        if isinstance(value, float) and np.isnan(value):
            return {}
    except TypeError:
        pass
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def json_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def safe_float(value: Any, default: float = 0.0) -> float:
    value = json_value(value)
    try:
        number = float(value)
        return number
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    value = json_value(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def date_value_series(df: pd.DataFrame | None, value_col: str = "close", limit: int = 42) -> list[dict[str, Any]]:
    """Serialize a date/value DataFrame into a compact chart series."""
    if df is None or len(df) == 0 or value_col not in df.columns:
        return []

    data = df.copy()
    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
    elif data.index.name:
        data = data.reset_index().rename(columns={data.index.name: "date"})
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
    else:
        data = data.reset_index().rename(columns={"index": "date"})
        data["date"] = pd.to_datetime(data["date"], errors="coerce")

    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=["date", value_col]).sort_values("date").tail(limit)
    return [{"date": str(r["date"])[:10], "value": round(safe_float(r[value_col]), 4)} for _, r in data.iterrows()]


def series_card(
    key: str,
    label: str,
    symbol: str,
    df: pd.DataFrame | None,
    value_col: str = "close",
    unit: str = "",
    data_source: str = "real",
    source_detail: str = "",
    series_limit: int = 42,
) -> dict[str, Any]:
    """Build the standard market card payload from a date/value series."""
    series = date_value_series(df, value_col=value_col, limit=series_limit)
    latest = series[-1]["value"] if series else None
    prev = series[-2]["value"] if len(series) > 1 else latest
    change = (latest - prev) if latest is not None and prev is not None else 0
    change_pct = (change / prev) if prev else 0
    return {
        "key": key,
        "label": label,
        "symbol": symbol,
        "value": latest,
        "change": round(change, 4),
        "change_pct": round(change_pct, 4),
        "unit": unit,
        "series": series,
        "data_source": data_source,
        "source_detail": source_detail,
    }
