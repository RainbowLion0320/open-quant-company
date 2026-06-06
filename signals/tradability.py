"""Tradability filters shared by signal selection and execution."""

from __future__ import annotations

import re
from typing import Mapping


SPECIAL_TREATMENT_RE = re.compile(r"(^|\*)ST|退", re.IGNORECASE)


def is_tradable_stock(symbol: str, name: str = "") -> bool:
    text = str(name or "").replace(" ", "").upper()
    if SPECIAL_TREATMENT_RE.search(text):
        return False
    return bool(str(symbol or "").strip())


def is_tradable_signal(row: Mapping) -> bool:
    return is_tradable_stock(str(row.get("symbol", "")), str(row.get("name", "")))
