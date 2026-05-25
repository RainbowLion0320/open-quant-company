"""Shared helpers for system API service modules."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd


def json_map(value) -> dict:
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


def json_value(value):
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


def safe_int(value, default: int = 0) -> int:
    value = json_value(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default: float = 0.0) -> float:
    value = json_value(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
