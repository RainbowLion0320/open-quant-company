"""Shared helpers for CodeGraph read-only services."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def bounded_limit(limit: int, default: int, maximum: int) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def normalize_root(root: str) -> str:
    return (root or "").strip().strip("/").removeprefix("file:")


def top_module(path: str) -> str:
    return (path or "root").split("/", 1)[0] or "root"


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con
