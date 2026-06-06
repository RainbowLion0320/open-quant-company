"""Market regime feature and label construction."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from cybernetics.regime_scoring import breadth_strength, clamp, volume_strength
from research.forward_labels import (
    build_forward_labels as _shared_build_forward_labels,
    build_profit_labels as _shared_build_profit_labels,
)

def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Return a sorted OHLCV frame with datetime index and numeric close/volume."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["close", "volume", "amount"])
    data = df.copy()
    data.columns = [str(c).lower() for c in data.columns]
    if "close" not in data.columns and "收盘" in df.columns:
        data["close"] = df["收盘"]
    if "volume" not in data.columns and "成交量" in df.columns:
        data["volume"] = df["成交量"]
    if "amount" not in data.columns and "成交额" in df.columns:
        data["amount"] = df["成交额"]

    if "date" in data.columns:
        dates = pd.to_datetime(data["date"], errors="coerce")
    elif "trade_date" in data.columns:
        dates = pd.to_datetime(data["trade_date"], errors="coerce")
    else:
        dates = pd.to_datetime(data.index, errors="coerce")

    data = data.assign(date=dates).dropna(subset=["date"])
    data["close"] = pd.to_numeric(data.get("close"), errors="coerce")
    if "volume" in data.columns:
        data["volume"] = pd.to_numeric(data["volume"], errors="coerce").fillna(0.0)
    elif "vol" in data.columns:
        data["volume"] = pd.to_numeric(data["vol"], errors="coerce").fillna(0.0)
    else:
        data["volume"] = 0.0
    if "amount" in data.columns:
        data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
    else:
        data["amount"] = data["volume"] * data["close"]
    data = data.dropna(subset=["close"]).sort_values("date").set_index("date")
    return data[["close", "volume", "amount"]]


def build_forward_labels(close: pd.Series, horizons: Iterable[int] = (5, 20, 60)) -> pd.DataFrame:
    """Build forward labels from rows after each feature date."""
    return _shared_build_forward_labels(close, horizons)


def build_regime_feature_history(
    index_df: pd.DataFrame,
    breadth_history: pd.DataFrame | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Build point-in-time regime features from benchmark and optional breadth history."""
    data = normalize_ohlcv(index_df)
    if data.empty:
        return pd.DataFrame()
    if start:
        data = data[data.index >= pd.Timestamp(start)]
    if end and end != "auto":
        data = data[data.index <= pd.Timestamp(end)]
    if len(data) < 130:
        return pd.DataFrame()

    close = data["close"]
    ret1 = close.pct_change()
    ret20 = close.pct_change(20)
    ret60 = close.pct_change(60)
    ma20 = close.rolling(20, min_periods=20).mean()
    ma60 = close.rolling(60, min_periods=60).mean()
    ma120 = close.rolling(120, min_periods=120).mean()

    trend_raw = (
        0.25 * (close > ma20).astype(float)
        + 0.25 * (ma20 > ma60).astype(float)
        + 0.20 * (ma60 > ma120).astype(float)
        + 0.15 * (0.5 + (ret20 / 0.12)).map(clamp)
        + 0.15 * (0.5 + (ret60 / 0.25)).map(clamp)
    )

    realized_vol_20d = ret1.rolling(20, min_periods=10).std() * np.sqrt(252)
    rolling_peak = close.rolling(60, min_periods=20).max()
    drawdown_60d = close / rolling_peak - 1.0
    vol_score = 1.0 - ((realized_vol_20d - 0.12) / 0.28).map(clamp)
    drawdown_score = 1.0 - (drawdown_60d.clip(upper=0).abs() / 0.15).map(clamp)
    risk_raw = (0.60 * drawdown_score + 0.40 * vol_score).map(clamp)

    amount = data["amount"].replace(0, np.nan).fillna(data["volume"] * close)
    amount_5d = amount.rolling(5, min_periods=3).mean()
    amount_20d = amount.rolling(20, min_periods=10).mean()
    amount_ratio = (amount_5d / amount_20d).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    index_volume_raw = (0.5 + (amount_ratio - 1.0) * 0.5).map(clamp)

    proxy_advance = ret1.gt(0).rolling(20, min_periods=5).mean().fillna(0.5)
    proxy_above20 = (close > ma20).astype(float).rolling(20, min_periods=5).mean().fillna(0.5)
    proxy_above60 = (close > ma60).astype(float).rolling(60, min_periods=10).mean().fillna(0.5)
    proxy_above120 = (close > ma120).astype(float).rolling(120, min_periods=20).mean().fillna(0.5)

    features = pd.DataFrame(
        {
            "trend_raw": trend_raw,
            "risk_raw": risk_raw,
            "advance_ratio": proxy_advance,
            "above_ma20": proxy_above20,
            "above_ma60": proxy_above60,
            "above_ma120": proxy_above120,
            "sample_size": 0.0,
            "amount_ratio_5_20": amount_ratio,
            "up_amount_ratio": proxy_advance,
            "realized_vol_20d": realized_vol_20d,
            "drawdown_60d": drawdown_60d,
            "volume_raw": index_volume_raw,
        },
        index=data.index,
    )

    if breadth_history is not None and not breadth_history.empty:
        breadth = breadth_history.copy()
        breadth.index = pd.to_datetime(breadth.index)
        breadth = breadth.reindex(features.index).ffill()
        for col in [
            "advance_ratio",
            "above_ma20",
            "above_ma60",
            "above_ma120",
            "sample_size",
            "amount_ratio_5_20",
            "up_amount_ratio",
        ]:
            if col in breadth:
                features[col] = breadth[col].where(breadth[col].notna(), features[col])

    features["breadth_raw"] = [
        breadth_strength(row.advance_ratio, row.above_ma20, row.above_ma60, row.above_ma120)
        for row in features.itertuples()
    ]
    volume_values = []
    for row in features.itertuples():
        value, _trend, _detail = volume_strength(
            amount_ratio_5_20=float(row.amount_ratio_5_20),
            advance_ratio=float(row.advance_ratio),
            up_amount_ratio=float(row.up_amount_ratio),
            index_volume=float(row.volume_raw),
            sample_size=int(row.sample_size),
        )
        volume_values.append(value)
    features["volume_raw"] = volume_values
    features = features.replace([np.inf, -np.inf], np.nan).dropna(subset=["trend_raw", "breadth_raw", "risk_raw", "volume_raw"])
    return features


def load_full_market_breadth_history(
    *,
    start: str | None = None,
    end: str | None = None,
    daily_dir: str | Path | None = None,
) -> pd.DataFrame:
    """Load historical full-market breadth from local stock daily parquet files."""
    try:
        import duckdb
    except Exception:
        return pd.DataFrame()

    if daily_dir is None:
        from data.storage.datahub import get_datahub

        daily_dir = get_datahub().store_path("stock") / "daily"
    daily_path = Path(daily_dir)
    if not daily_path.exists():
        return pd.DataFrame()

    source_sql = "'" + str(daily_path / "*.parquet").replace("'", "''") + "'"
    warmup_start = pd.Timestamp(start) - pd.Timedelta(days=240) if start else None
    where = ["date is not null", "close is not null"]
    if warmup_start is not None:
        where.append(f"cast(date as date) >= date '{warmup_start.date()}'")
    if end and end != "auto":
        where.append(f"cast(date as date) <= date '{pd.Timestamp(end).date()}'")
    where_sql = " and ".join(where)
    query = f"""
    with rows as (
      select
        filename,
        cast(date as date) as trade_date,
        cast(close as double) as close,
        coalesce(try_cast(amount as double), try_cast(volume as double) * try_cast(close as double)) as amount
      from read_parquet({source_sql}, filename=true, union_by_name=true)
      where {where_sql}
    ), enriched as (
      select
        *,
        lag(close) over(partition by filename order by trade_date) as prev_close,
        avg(close) over(partition by filename order by trade_date rows between 19 preceding and current row) as ma20,
        avg(close) over(partition by filename order by trade_date rows between 59 preceding and current row) as ma60,
        avg(close) over(partition by filename order by trade_date rows between 119 preceding and current row) as ma120,
        count(close) over(partition by filename order by trade_date rows between 19 preceding and current row) as n20,
        count(close) over(partition by filename order by trade_date rows between 59 preceding and current row) as n60,
        count(close) over(partition by filename order by trade_date rows between 119 preceding and current row) as n120
      from rows
    ), daily as (
      select
        trade_date,
        count(*) filter(where prev_close is not null and prev_close > 0) as sample_size,
        count(*) filter(where close > prev_close and prev_close > 0) as up_count,
        count(*) filter(where close < prev_close and prev_close > 0) as down_count,
        count(*) filter(where close = prev_close and prev_close > 0) as unchanged_count,
        count(*) filter(where n20 >= 20 and close > ma20) as above_ma20,
        count(*) filter(where n20 >= 20) as eligible_ma20,
        count(*) filter(where n60 >= 60 and close > ma60) as above_ma60,
        count(*) filter(where n60 >= 60) as eligible_ma60,
        count(*) filter(where n120 >= 120 and close > ma120) as above_ma120,
        count(*) filter(where n120 >= 120) as eligible_ma120,
        sum(amount) filter(where amount is not null and amount > 0) as total_amount,
        sum(amount) filter(where amount is not null and amount > 0 and close > prev_close and prev_close > 0) as up_amount
      from enriched
      group by trade_date
      order by trade_date
    )
    select * from daily
    """
    try:
        df = duckdb.connect(database=":memory:").execute(query).df()
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return pd.DataFrame()

    df["date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("date").sort_index()
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    traded = df[["up_count", "down_count", "unchanged_count"]].sum(axis=1)
    out = pd.DataFrame(index=df.index)
    out["sample_size"] = df["sample_size"].astype(float)
    out["advance_ratio"] = (df["up_count"] / traded.replace(0, np.nan)).fillna(0.5)
    out["above_ma20"] = (df["above_ma20"] / df["eligible_ma20"].replace(0, np.nan)).fillna(0.5)
    out["above_ma60"] = (df["above_ma60"] / df["eligible_ma60"].replace(0, np.nan)).fillna(0.5)
    out["above_ma120"] = (df["above_ma120"] / df["eligible_ma120"].replace(0, np.nan)).fillna(0.5)
    total_amount = df["total_amount"].replace(0, np.nan)
    out["amount_ratio_5_20"] = (total_amount.rolling(5, min_periods=3).mean() / total_amount.rolling(20, min_periods=10).mean()).fillna(1.0)
    out["up_amount_ratio"] = (df["up_amount"] / total_amount).fillna(out["advance_ratio"]).fillna(0.5)
    return out


def build_profit_labels(asset_panel: pd.DataFrame, horizons: Iterable[int] = (5, 20, 60)) -> pd.DataFrame:
    """Build forward money-making labels from tradable assets only."""
    return _shared_build_profit_labels(asset_panel, horizons)
