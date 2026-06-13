"""Tencent Finance candidate-source parsers.

These helpers only parse observed public web responses for capability probes.
They are not production data adapters and do not write into DataHub.
"""

from __future__ import annotations

import re
from typing import Any


_QUOTE_RE = re.compile(r'v_(?P<symbol>[a-z]{2}\d{6})="(?P<body>.*)";?$')
_TIMESTAMP_RE = re.compile(r"^\d{14}$")


def parse_realtime_quote(text: str) -> dict[str, Any]:
    """Parse a ``qt.gtimg.cn`` realtime quote payload."""
    match = _QUOTE_RE.match(text.strip())
    if not match:
        raise ValueError("unrecognized Tencent realtime quote payload")
    fields = match.group("body").split("~")
    if len(fields) < 7:
        raise ValueError("Tencent realtime quote payload has too few fields")
    timestamp = next((field for field in reversed(fields) if _TIMESTAMP_RE.match(field)), "")
    return {
        "source": "tencent_finance",
        "symbol": match.group("symbol"),
        "name": fields[1],
        "code": fields[2],
        "last_price": _to_float(fields[3]),
        "previous_close": _to_float(fields[4]),
        "open": _to_float(fields[5]),
        "volume": _to_float(fields[6]),
        "timestamp": timestamp,
    }


def parse_fqkline_payload(payload: dict[str, Any], *, symbol: str, adjust: str = "qfq") -> list[dict[str, Any]]:
    """Parse a Tencent ``appstock/app/fqkline/get`` response."""
    if int(payload.get("code", -1)) != 0:
        raise ValueError(f"Tencent fqkline returned code={payload.get('code')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("Tencent fqkline payload missing data object")
    symbol_data = data.get(symbol)
    if not isinstance(symbol_data, dict):
        raise ValueError(f"Tencent fqkline payload missing symbol: {symbol}")
    rows = symbol_data.get(f"{adjust}day") or symbol_data.get("day")
    if not isinstance(rows, list):
        raise ValueError("Tencent fqkline payload missing day rows")
    parsed = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        parsed.append(
            {
                "source": "tencent_finance",
                "symbol": symbol,
                "adjust": adjust,
                "date": str(row[0]),
                "open": _to_float(row[1]),
                "close": _to_float(row[2]),
                "high": _to_float(row[3]),
                "low": _to_float(row[4]),
                "volume": _to_float(row[5]),
            }
        )
    if not parsed:
        raise ValueError("Tencent fqkline payload contained no parsable rows")
    return parsed


def _to_float(value: Any) -> float | None:
    try:
        text = str(value).strip()
        return float(text) if text else None
    except (TypeError, ValueError):
        return None
