"""Symbol normalization and exchange-code helpers."""

from __future__ import annotations


def normalize_symbol(symbol: object) -> str:
    """Normalize A-share symbols to six-digit plain codes when possible."""
    text = str(symbol).strip()
    text = text.replace(".SH", "").replace(".SZ", "").replace(".sh", "").replace(".sz", "")
    if text.lower().startswith(("sh", "sz")):
        text = text[2:]
    return text.zfill(6) if text.isdigit() else text


def infer_exchange(symbol: object) -> str:
    """Infer Tushare exchange suffix from a plain A-share code."""
    code = normalize_symbol(symbol)
    if code.startswith(("43", "83", "87", "88", "92")):
        return "BJ"
    return "SH" if code.startswith(("5", "6", "9")) else "SZ"


def to_sina_symbol(symbol: object) -> str:
    """Convert to Sina/AKShare index style, e.g. ``600519`` -> ``sh600519``."""
    code = normalize_symbol(symbol)
    return f"{infer_exchange(code).lower()}{code}"


def to_ts_code(symbol: object) -> str:
    """Convert to Tushare style, e.g. ``600519`` -> ``600519.SH``."""
    code = normalize_symbol(symbol)
    return f"{code}.{infer_exchange(code)}"
