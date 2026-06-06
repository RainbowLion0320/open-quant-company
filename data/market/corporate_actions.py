"""Normalized corporate-action events and position adjustment helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from data.storage.datahub import DataHub, get_datahub


STANDARD_COLUMNS = [
    "symbol",
    "ex_date",
    "cash_dividend_per_share",
    "share_multiplier",
    "source",
]

DATE_ALIASES = (
    "ex_date",
    "exdiv_date",
    "除权除息日",
    "record_date",
    "股权登记日",
    "pay_date",
    "派息日",
    "ann_date",
    "公告日期",
)
CASH_ALIASES = (
    "cash_dividend_per_share",
    "cash_dividend",
    "cash_div",
    "cash_div_tax",
    "每股派息",
    "派息",
)
SHARE_MULTIPLIER_ALIASES = (
    "share_multiplier",
    "split_multiplier",
)
PER_SHARE_BONUS_ALIASES = (
    "stk_div",
    "stk_bo_rate",
    "stk_co_rate",
    "bonus_share_ratio",
    "transfer_share_ratio",
    "stock_dividend_per_share",
    "每股送股",
    "每股转增",
)
PER_TEN_BONUS_ALIASES = (
    "send_share_per_10",
    "transfer_share_per_10",
    "每10股送",
    "每10股转增",
)


@dataclass(frozen=True)
class PositionAdjustmentResult:
    shares: float | int
    cash: float
    events_applied: int


def _empty_events() -> pd.DataFrame:
    return pd.DataFrame(columns=STANDARD_COLUMNS).astype(
        {
            "symbol": "object",
            "cash_dividend_per_share": "float64",
            "share_multiplier": "float64",
            "source": "object",
        }
    )


def _first_existing(columns: Iterable[str], aliases: Iterable[str]) -> str | None:
    available = set(columns)
    return next((alias for alias in aliases if alias in available), None)


def _normalize_symbol(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "." in text:
        return text.split(".", 1)[0]
    return text


def _symbol_candidates(symbol: str) -> set[str]:
    base = _normalize_symbol(symbol)
    candidates = {base, symbol}
    if len(base) == 6 and base.isdigit():
        suffix = "SH" if base.startswith(("5", "6", "9")) else "SZ"
        candidates.add(f"{base}.{suffix}")
    return {item for item in candidates if item}


def _numeric_series(frame: pd.DataFrame, column: str | None, default: float = 0.0) -> pd.Series:
    if column is None or column not in frame.columns:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").fillna(default).astype("float64")


def _date_series(frame: pd.DataFrame, column: str | None) -> pd.Series:
    if column is None or column not in frame.columns:
        return pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    return pd.to_datetime(frame[column], errors="coerce")


def _share_multiplier(frame: pd.DataFrame) -> pd.Series:
    explicit = _first_existing(frame.columns, SHARE_MULTIPLIER_ALIASES)
    if explicit:
        return _numeric_series(frame, explicit, default=1.0).replace(0.0, 1.0)

    bonus = pd.Series(0.0, index=frame.index, dtype="float64")
    for column in PER_SHARE_BONUS_ALIASES:
        if column in frame.columns:
            bonus = bonus + _numeric_series(frame, column)
    for column in PER_TEN_BONUS_ALIASES:
        if column in frame.columns:
            bonus = bonus + _numeric_series(frame, column) / 10.0
    return 1.0 + bonus


def normalize_dividend_events(df: pd.DataFrame | None, symbol: str | None = None) -> pd.DataFrame:
    """Convert raw dividend rows into the project's corporate-action event schema."""
    if df is None or df.empty:
        return _empty_events()

    frame = df.copy()
    symbol_col = _first_existing(frame.columns, ("symbol", "ts_code", "code"))
    date_col = _first_existing(frame.columns, DATE_ALIASES)
    cash_col = _first_existing(frame.columns, CASH_ALIASES)

    if symbol_col:
        symbols = frame[symbol_col].map(_normalize_symbol)
    else:
        symbols = pd.Series(_normalize_symbol(symbol), index=frame.index, dtype="object")

    out = pd.DataFrame(
        {
            "symbol": symbols,
            "ex_date": _date_series(frame, date_col),
            "cash_dividend_per_share": _numeric_series(frame, cash_col),
            "share_multiplier": _share_multiplier(frame),
            "source": frame["source"] if "source" in frame.columns else "dividend",
        }
    )
    if symbol:
        candidates = {_normalize_symbol(item) for item in _symbol_candidates(symbol)}
        out = out[out["symbol"].isin(candidates)]
    out = out.dropna(subset=["ex_date"]).copy()
    out = out.sort_values(["symbol", "ex_date"]).reset_index(drop=True)
    return out[STANDARD_COLUMNS]


def _read_all_dividends(hub: DataHub) -> pd.DataFrame:
    try:
        path = hub.dimension_path("dividend")
    except Exception:
        path = hub.store_path("stock") / "dividend" / "all_dividends.parquet"
    frame = hub.read_parquet(path, default=pd.DataFrame())
    return frame if frame is not None else pd.DataFrame()


def load_corporate_actions(symbol: str, *, hub: DataHub | None = None) -> pd.DataFrame:
    """Load normalized corporate-action events for one stock symbol."""
    store = hub or get_datahub()
    path = store.stock_corporate_actions_path(symbol)
    frame = store.read_parquet(path, default=pd.DataFrame())
    if frame is not None and not frame.empty:
        return normalize_dividend_events(frame, symbol=symbol)
    return normalize_dividend_events(_read_all_dividends(store), symbol=symbol)


def _parse_boundary(value: str | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else pd.Timestamp(parsed)


def _maybe_int(value: float) -> float | int:
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return int(rounded)
    return value


def apply_corporate_actions_to_position(
    *,
    symbol: str,
    shares: float,
    cash: float = 0.0,
    actions: pd.DataFrame | None = None,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
    hub: DataHub | None = None,
) -> PositionAdjustmentResult:
    """Apply cash dividends and share multipliers to a historical position."""
    events = normalize_dividend_events(actions, symbol=symbol) if actions is not None else load_corporate_actions(symbol, hub=hub)
    if events.empty:
        return PositionAdjustmentResult(shares=_maybe_int(float(shares)), cash=float(cash), events_applied=0)

    start = _parse_boundary(start_date)
    end = _parse_boundary(end_date)
    if start is not None:
        events = events[events["ex_date"] > start]
    if end is not None:
        events = events[events["ex_date"] <= end]

    current_shares = float(shares)
    current_cash = float(cash)
    applied = 0
    for event in events.sort_values("ex_date").itertuples(index=False):
        current_cash += current_shares * float(event.cash_dividend_per_share)
        current_shares *= float(event.share_multiplier)
        applied += 1

    return PositionAdjustmentResult(
        shares=_maybe_int(current_shares),
        cash=current_cash,
        events_applied=applied,
    )
