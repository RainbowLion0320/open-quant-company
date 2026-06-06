"""Shared return/date normalization and sector turnover amount helpers."""
from __future__ import annotations

import pandas as pd


def _normalize_return_series(df: pd.DataFrame) -> pd.Series:
    if "pct_chg" in df.columns:
        series = pd.to_numeric(df["pct_chg"], errors="coerce")
        if series.abs().median(skipna=True) > 1:
            series = series / 100.0
        return series
    if "return_1d" in df.columns:
        return pd.to_numeric(df["return_1d"], errors="coerce")
    if "close" in df.columns:
        return pd.to_numeric(df["close"], errors="coerce").pct_change()
    return pd.Series(dtype="float64")


def _normalize_date_series(df: pd.DataFrame) -> pd.Series:
    date_col = next((c for c in ("date", "trade_date") if c in df.columns), "")
    if not date_col:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    raw = df[date_col]
    raw_str = raw.astype(str).str.replace(r"\.0$", "", regex=True)
    yyyymmdd = raw_str.str.fullmatch(r"\d{8}")
    if yyyymmdd.any():
        normalized = raw_str.copy()
        normalized.loc[yyyymmdd] = (
            raw_str.loc[yyyymmdd].str.slice(0, 4)
            + "-"
            + raw_str.loc[yyyymmdd].str.slice(4, 6)
            + "-"
            + raw_str.loc[yyyymmdd].str.slice(6, 8)
        )
        return normalized
    parsed = pd.to_datetime(raw_str, errors="coerce")
    if parsed.notna().any():
        return parsed.dt.date.astype(str)
    return raw_str.str.slice(0, 10)


def _amount_col(df: pd.DataFrame) -> str:
    candidates = (
        "amount", "turnover_amount", "成交额", "成交额(元)", "成交金额",
        "amt", "money", "volume_amount",
    )
    return next((c for c in candidates if c in df.columns), "")


def _amount_series(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype="float64")

    col = _amount_col(df)
    if col:
        values = pd.to_numeric(df[col], errors="coerce")
    elif {"close", "volume"}.issubset(df.columns):
        values = pd.to_numeric(df["close"], errors="coerce") * pd.to_numeric(df["volume"], errors="coerce")
    else:
        return pd.Series(dtype="float64")

    index = df["_date"] if "_date" in df.columns else _normalize_date_series(df)
    series = pd.Series(values.to_numpy(), index=index)
    return pd.to_numeric(series, errors="coerce").dropna()


def _empty_amount_metrics() -> dict:
    return {"turnover_amount": 0.0, "amount_5d_avg": 0.0, "amount_source": "missing"}


def _amount_metrics(df: pd.DataFrame, source: str) -> dict:
    amount = _amount_series(df)
    if amount.empty:
        return _empty_amount_metrics()
    tail = amount.tail(5)
    return {
        "turnover_amount": float(tail.iloc[-1]),
        "amount_5d_avg": float(tail.mean()),
        "amount_source": source,
    }


def _aggregate_amount_metrics(series_list: list[pd.Series], source: str) -> dict:
    if not series_list:
        return _empty_amount_metrics()
    amount_df = pd.concat(series_list, axis=1).fillna(0)
    daily_total = amount_df.sum(axis=1).sort_index()
    if daily_total.empty:
        return _empty_amount_metrics()
    tail = daily_total.tail(5)
    return {
        "turnover_amount": float(tail.iloc[-1]),
        "amount_5d_avg": float(tail.mean()),
        "amount_source": source,
    }
