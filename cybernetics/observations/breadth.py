"""Full-market breadth observation helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence
import math
import os
import time

from cybernetics.config import _load_config
from cybernetics.regime_scoring import breadth_strength as _score_breadth_strength
from cybernetics.types import MarketBreadth
from cybernetics.observations.sources import _frame_close_volume, _stock_daily_files, _stock_daily_source_sql

_BREADTH_CACHE: Dict[str, Any] = {"expires_at": 0.0, "snapshot": None}

def _compute_full_market_breadth_duckdb(files: Optional[Sequence[Any]] = None) -> Optional[MarketBreadth]:
    try:
        import duckdb
    except Exception:
        return None

    source_sql = _stock_daily_source_sql(files)
    if source_sql is None:
        return MarketBreadth()

    query = f"""
    with ranked as (
      select
        filename,
        cast(date as varchar) as trade_date,
        cast(close as double) as close,
        row_number() over(partition by filename order by date desc) as rn
      from read_parquet({source_sql}, filename=true)
      where close is not null
    ), agg as (
      select
        filename,
        max(case when rn = 1 then trade_date end) as as_of,
        max(case when rn = 1 then close end) as last_close,
        max(case when rn = 2 then close end) as prev_close,
        avg(case when rn <= 20 then close end) as ma20,
        avg(case when rn <= 60 then close end) as ma60,
        avg(case when rn <= 120 then close end) as ma120,
        count(case when rn <= 20 then 1 end) as n20,
        count(case when rn <= 60 then 1 end) as n60,
        count(case when rn <= 120 then 1 end) as n120
      from ranked
      where rn <= 130
      group by filename
    )
    select
      count(*) filter(where last_close is not null and prev_close is not null and prev_close > 0) as sample_size,
      count(*) filter(where last_close > prev_close and prev_close > 0) as up_count,
      count(*) filter(where last_close < prev_close and prev_close > 0) as down_count,
      count(*) filter(where last_close = prev_close and prev_close > 0) as unchanged_count,
      count(*) filter(where n20 >= 20 and last_close > ma20) as above_ma20,
      count(*) filter(where n20 >= 20) as eligible_ma20,
      count(*) filter(where n60 >= 60 and last_close > ma60) as above_ma60,
      count(*) filter(where n60 >= 60) as eligible_ma60,
      count(*) filter(where n120 >= 120 and last_close > ma120) as above_ma120,
      count(*) filter(where n120 >= 120) as eligible_ma120,
      max(as_of) as as_of
    from agg
    """

    try:
        row = duckdb.connect(database=":memory:").execute(query).fetchone()
    except Exception:
        return None

    if not row:
        return MarketBreadth()

    (
        sample_size,
        up_count,
        down_count,
        unchanged_count,
        above_ma20,
        eligible_ma20,
        above_ma60,
        eligible_ma60,
        above_ma120,
        eligible_ma120,
        as_of,
    ) = row

    sample_size = int(sample_size or 0)
    up_count = int(up_count or 0)
    down_count = int(down_count or 0)
    unchanged_count = int(unchanged_count or 0)
    traded = up_count + down_count + unchanged_count

    return MarketBreadth(
        advance_ratio=(up_count / traded) if traded else 0.5,
        above_ma20=(int(above_ma20 or 0) / int(eligible_ma20)) if eligible_ma20 else 0.5,
        above_ma60=(int(above_ma60 or 0) / int(eligible_ma60)) if eligible_ma60 else 0.5,
        above_ma120=(int(above_ma120 or 0) / int(eligible_ma120)) if eligible_ma120 else 0.5,
        sample_size=sample_size,
        up_count=up_count,
        down_count=down_count,
        unchanged_count=unchanged_count,
        as_of=str(as_of)[:10] if as_of else "",
    )

def _read_breadth_observation(path) -> Optional[Dict[str, Any]]:
    import pandas as pd

    try:
        try:
            df = pd.read_parquet(path, columns=["date", "close"])
        except Exception:
            df = pd.read_parquet(path, columns=["close"])
    except Exception:
        return None

    data = _frame_close_volume(df)
    if len(data) < 2:
        return None

    closes = data["close"].tail(130)
    if len(closes) < 2:
        return None

    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])
    if not math.isfinite(last) or not math.isfinite(prev) or prev <= 0:
        return None

    result = {
        "last": last,
        "prev": prev,
        "direction": 1 if last > prev else (-1 if last < prev else 0),
        "above_ma20": False,
        "above_ma60": False,
        "above_ma120": False,
        "has_ma20": False,
        "has_ma60": False,
        "has_ma120": False,
        "as_of": "",
    }

    if "date" in data.columns and len(data):
        result["as_of"] = str(data["date"].iloc[-1])[:10]

    for window in (20, 60, 120):
        if len(closes) >= window:
            ma = float(closes.tail(window).mean())
            result[f"has_ma{window}"] = math.isfinite(ma) and ma > 0
            result[f"above_ma{window}"] = bool(result[f"has_ma{window}"] and last > ma)

    return result

def _compute_full_market_breadth(
    files: Optional[Sequence[Any]] = None,
    *,
    use_cache: bool = True,
) -> MarketBreadth:
    """
    Compute full-market A-share breadth from local stock daily parquet files.

    The dashboard calls regime endpoints frequently, so the expensive full scan
    is cached in memory for a short TTL. This still avoids implicit network
    fetches and keeps breadth tied to the local DataHub snapshot.
    """
    now = time.monotonic()
    try:
        det_cfg = _load_config()["adaptive"]["detection"]
        ttl = int(det_cfg.get("breadth_cache_ttl_seconds", 900))
        workers = int(det_cfg.get("breadth_workers", min(8, os.cpu_count() or 4)))
    except Exception:
        ttl = 900
        workers = min(8, os.cpu_count() or 4)

    if use_cache and _BREADTH_CACHE.get("snapshot") is not None and _BREADTH_CACHE.get("expires_at", 0.0) > now:
        return _BREADTH_CACHE["snapshot"]

    source_files = list(files) if files is not None else None
    if source_files is not None and not source_files:
        return MarketBreadth()

    snapshot = _compute_full_market_breadth_duckdb(source_files)
    if snapshot is not None:
        if use_cache:
            _BREADTH_CACHE["snapshot"] = snapshot
            _BREADTH_CACHE["expires_at"] = now + ttl
        return snapshot

    source_files = source_files if source_files is not None else _stock_daily_files()
    if not source_files:
        return MarketBreadth()

    from concurrent.futures import ThreadPoolExecutor

    up_count = down_count = unchanged_count = 0
    above = {20: 0, 60: 0, 120: 0}
    eligible = {20: 0, 60: 0, 120: 0}
    sample_size = 0
    as_of = ""

    max_workers = max(1, min(workers, len(source_files)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for obs in executor.map(_read_breadth_observation, source_files):
            if not obs:
                continue
            sample_size += 1
            if obs["direction"] > 0:
                up_count += 1
            elif obs["direction"] < 0:
                down_count += 1
            else:
                unchanged_count += 1
            for window in (20, 60, 120):
                if obs.get(f"has_ma{window}"):
                    eligible[window] += 1
                    if obs.get(f"above_ma{window}"):
                        above[window] += 1
            if obs.get("as_of"):
                as_of = max(as_of, str(obs["as_of"]))

    traded = up_count + down_count + unchanged_count
    snapshot = MarketBreadth(
        advance_ratio=(up_count / traded) if traded else 0.5,
        above_ma20=(above[20] / eligible[20]) if eligible[20] else 0.5,
        above_ma60=(above[60] / eligible[60]) if eligible[60] else 0.5,
        above_ma120=(above[120] / eligible[120]) if eligible[120] else 0.5,
        sample_size=sample_size,
        up_count=up_count,
        down_count=down_count,
        unchanged_count=unchanged_count,
        as_of=as_of,
    )

    if use_cache:
        _BREADTH_CACHE["snapshot"] = snapshot
        _BREADTH_CACHE["expires_at"] = now + ttl
    return snapshot

def _breadth_strength(breadth: MarketBreadth) -> float:
    return _score_breadth_strength(
        breadth.advance_ratio,
        breadth.above_ma20,
        breadth.above_ma60,
        breadth.above_ma120,
    )
