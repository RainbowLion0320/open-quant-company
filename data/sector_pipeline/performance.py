"""Sector performance snapshots from SW index data or stock proxy returns."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from data.datahub import DataHub
from data.sector_pipeline.amounts import (
    _aggregate_amount_metrics,
    _amount_metrics,
    _amount_series,
    _empty_amount_metrics,
    _normalize_date_series,
    _normalize_return_series,
)
from data.sector_pipeline.membership import SW_INDUSTRIES, _snapshot_path


def _period_return(returns: pd.Series, days: int) -> float:
    if len(returns) < days:
        return 0.0
    window = pd.to_numeric(returns.tail(days), errors="coerce").dropna()
    if window.empty:
        return 0.0
    return float((1.0 + window).prod() - 1.0)


def build_sector_performance(hub: DataHub | None = None, lookback_days: int = 120) -> pd.DataFrame:
    """Build sector-level performance from cached SW index data or stock proxy."""
    hub = hub or DataHub()

    mem_path = hub.dimension_path("sector_membership")
    if not mem_path.exists():
        return pd.DataFrame()

    mem = hub.read_parquet(mem_path, default=pd.DataFrame())
    if mem.empty:
        return pd.DataFrame()

    today = date.today()
    rows = []
    for sector_code, sector_name in SW_INDUSTRIES.items():
        sector_symbols = mem[mem["sector_code"] == sector_code]["symbol"].tolist()
        sector_ret, latest_date, data_source, data_count, amount_metrics = _load_sector_index_returns(
            hub, sector_code, lookback_days
        )
        if data_source == "real":
            data_count = len(sector_symbols)

        if sector_ret.empty:
            sector_ret, latest_date, data_count, amount_metrics = _build_proxy_returns(
                hub, sector_symbols, lookback_days
            )
            data_source = "proxy" if not sector_ret.empty else "missing"

        if sector_ret.empty:
            rows.append(_empty_sector_row(sector_code, sector_name, today))
            continue

        sector_vol = float(sector_ret.std() * np.sqrt(252)) if len(sector_ret) > 1 else 0.0
        ret_1d = float(sector_ret.iloc[-1]) if len(sector_ret) else 0.0
        rows.append({
            "sector_code": sector_code,
            "sector_name": sector_name,
            "date": today.isoformat(),
            "return_1d": round(ret_1d, 6),
            "return_5d": round(_period_return(sector_ret, 5), 6),
            "return_20d": round(_period_return(sector_ret, 20), 6),
            "return_60d": round(_period_return(sector_ret, 60), 6),
            "volatility": round(sector_vol, 4),
            "member_count": int(data_count),
            "turnover_amount": round(float(amount_metrics.get("turnover_amount", 0.0)), 2),
            "amount_5d_avg": round(float(amount_metrics.get("amount_5d_avg", 0.0)), 2),
            "amount_source": str(amount_metrics.get("amount_source", "missing")),
            "latest_date": latest_date,
            "data_source": data_source,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        total_amount = float(pd.to_numeric(df["amount_5d_avg"], errors="coerce").clip(lower=0).sum())
        if total_amount > 0:
            amount = pd.to_numeric(df["amount_5d_avg"], errors="coerce").fillna(0).clip(lower=0)
            df["amount_share"] = (amount / total_amount).round(4)
        else:
            df["amount_share"] = 0.0
        dest = _snapshot_path(hub, "sector_performance_snapshot", today)
        hub.write_parquet(df, dest, producer="sectors.build_performance")
    return df


def _load_sector_index_returns(
    hub: DataHub,
    sector_code: str,
    lookback_days: int,
) -> tuple[pd.Series, str, str, int, dict]:
    candidates: list[Path] = []
    for symbol in (sector_code, f"{sector_code}.SI"):
        try:
            candidates.append(hub.dimension_path("sector_sw_daily", symbol=symbol))
        except Exception:
            continue

    for path in candidates:
        if not path.exists():
            continue
        df = hub.read_parquet(path, default=pd.DataFrame())
        if df.empty:
            continue
        work = df.copy()
        work["_date"] = _normalize_date_series(df)
        sort_col = "trade_date" if "trade_date" in work.columns else "_date"
        work = work.sort_values(sort_col).tail(lookback_days)
        returns = _normalize_return_series(work).dropna()
        if returns.empty:
            continue
        latest_date = str(work["_date"].iloc[-1])[:10]
        return returns.reset_index(drop=True), latest_date, "real", len(work), _amount_metrics(work, source="real")
    return pd.Series(dtype="float64"), "", "missing", 0, _empty_amount_metrics()


def _build_proxy_returns(hub: DataHub, symbols: list[str], lookback_days: int) -> tuple[pd.Series, str, int, dict]:
    sector_returns = []
    sector_amounts = []
    latest_date = ""
    data_count = 0
    for symbol in symbols[:100]:
        try:
            ohlcv_path = hub.dimension_path("ohlcv_daily", symbol=symbol)
        except Exception:
            continue
        if not ohlcv_path.exists():
            continue
        df = hub.read_parquet(ohlcv_path, default=pd.DataFrame())
        if df.empty or "close" not in df.columns:
            continue
        work = df.copy()
        work["_date"] = _normalize_date_series(df)
        sort_col = "date" if "date" in work.columns else "_date"
        work = work.sort_values(sort_col).tail(lookback_days)
        if work.empty:
            continue
        returns = _normalize_return_series(work)
        sector_returns.append(pd.Series(returns.to_numpy(), index=work["_date"]))
        amount = _amount_series(work)
        if not amount.empty:
            sector_amounts.append(amount)
        data_count += 1
        last_date = str(work["_date"].iloc[-1])[:10]
        if not latest_date or last_date > latest_date:
            latest_date = last_date

    if not sector_returns:
        return pd.Series(dtype="float64"), "", 0, _empty_amount_metrics()

    ret_df = pd.concat(sector_returns, axis=1)
    sector_ret = ret_df.mean(axis=1).dropna()
    return sector_ret.reset_index(drop=True), latest_date, data_count, _aggregate_amount_metrics(sector_amounts, source="proxy")


def _empty_sector_row(code: str, name: str, today: date) -> dict:
    return {
        "sector_code": code,
        "sector_name": name,
        "date": today.isoformat(),
        "return_1d": 0.0,
        "return_5d": 0.0,
        "return_20d": 0.0,
        "return_60d": 0.0,
        "volatility": 0.0,
        "member_count": 0,
        "turnover_amount": 0.0,
        "amount_5d_avg": 0.0,
        "amount_share": 0.0,
        "amount_source": "missing",
        "latest_date": "",
        "data_source": "missing",
    }
