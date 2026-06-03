"""Full-market and index volume confirmation helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence
import time

from cybernetics.config import _load_config
from cybernetics.regime_scoring import volume_strength as _score_volume_strength
from cybernetics.types import MarketBreadth, MarketVolume
from cybernetics.observations.sources import _clamp, _frame_close_volume, _regime_indexes, _stock_daily_source_sql

_VOLUME_CACHE: Dict[str, Any] = {"expires_at": 0.0, "snapshot": None}

def _compute_full_market_volume_duckdb(files: Optional[Sequence[Any]] = None) -> Optional[MarketVolume]:
    try:
        import duckdb
    except Exception:
        return None

    source_sql = _stock_daily_source_sql(files)
    if source_sql is None:
        return MarketVolume()

    query = f"""
    with rows as (
      select
        filename,
        cast(date as date) as trade_date,
        cast(close as double) as close,
        cast(volume as double) as volume,
        coalesce(try_cast(amount as double), try_cast(volume as double) * try_cast(close as double)) as amount,
        lag(cast(close as double)) over(partition by filename order by cast(date as date)) as prev_close
      from read_parquet({source_sql}, filename=true, union_by_name=true)
      where date is not null and close is not null and volume is not null
    ), recent_dates as (
      select distinct trade_date
      from rows
      where amount is not null and amount > 0
      order by trade_date desc
      limit 25
    ), daily as (
      select
        r.trade_date,
        sum(r.amount) as total_amount,
        sum(case when r.close > r.prev_close then r.amount else 0 end) as up_amount,
        sum(case when r.close < r.prev_close then r.amount else 0 end) as down_amount,
        count(*) as sample_size
      from rows r
      join recent_dates d on r.trade_date = d.trade_date
      where r.amount is not null and r.amount > 0 and r.prev_close is not null and r.prev_close > 0
      group by r.trade_date
    ), ranked as (
      select
        *,
        row_number() over(order by trade_date desc) as rn
      from daily
    )
    select
      avg(total_amount) filter(where rn <= 5) as amount_5d,
      avg(total_amount) filter(where rn <= 20) as amount_20d,
      sum(up_amount) filter(where rn <= 5) as up_amount_5d,
      sum(total_amount) filter(where rn <= 5) as total_amount_5d,
      avg(sample_size) filter(where rn <= 5) as sample_size,
      max(trade_date) as as_of
    from ranked
    where rn <= 20
    """

    try:
        row = duckdb.connect(database=":memory:").execute(query).fetchone()
    except Exception:
        return None

    if not row:
        return MarketVolume()

    amount_5d, amount_20d, up_amount_5d, total_amount_5d, sample_size, as_of = row
    amount_5d = float(amount_5d or 0.0)
    amount_20d = float(amount_20d or 0.0)
    up_amount_5d = float(up_amount_5d or 0.0)
    total_amount_5d = float(total_amount_5d or 0.0)

    return MarketVolume(
        amount_ratio_5_20=(amount_5d / amount_20d) if amount_20d > 0 else 1.0,
        up_amount_ratio=(up_amount_5d / total_amount_5d) if total_amount_5d > 0 else 0.5,
        sample_size=int(sample_size or 0),
        amount_5d=amount_5d,
        amount_20d=amount_20d,
        as_of=str(as_of)[:10] if as_of else "",
    )

def _compute_full_market_volume(
    files: Optional[Sequence[Any]] = None,
    *,
    use_cache: bool = True,
) -> MarketVolume:
    now = time.monotonic()
    try:
        det_cfg = _load_config()["adaptive"]["detection"]
        ttl = int(det_cfg.get("breadth_cache_ttl_seconds", 900))
    except Exception:
        ttl = 900

    if use_cache and _VOLUME_CACHE.get("snapshot") is not None and _VOLUME_CACHE.get("expires_at", 0.0) > now:
        return _VOLUME_CACHE["snapshot"]

    source_files = list(files) if files is not None else None
    if source_files is not None and not source_files:
        return MarketVolume()

    snapshot = _compute_full_market_volume_duckdb(source_files)
    if snapshot is None:
        snapshot = MarketVolume()

    if use_cache:
        _VOLUME_CACHE["snapshot"] = snapshot
        _VOLUME_CACHE["expires_at"] = now + ttl
    return snapshot

def _index_volume_confirmation(df) -> Optional[Dict[str, float]]:
    data = _frame_close_volume(df)
    if "volume" not in data.columns or len(data) < 20:
        return None

    volume = data["volume"].dropna()
    if len(volume) < 20:
        return None

    vol_5 = float(volume.tail(5).mean())
    vol_20 = float(volume.tail(20).mean())
    if vol_20 <= 0:
        return None

    vol_ratio = vol_5 / vol_20
    close = data["close"]
    ret_5 = (float(close.iloc[-1]) / float(close.iloc[-6]) - 1.0) if len(close) >= 6 and float(close.iloc[-6]) > 0 else 0.0
    if ret_5 > 0.01:
        strength = 0.5 + (vol_ratio - 1.0) * 0.8
    elif ret_5 < -0.01:
        strength = 0.5 - (vol_ratio - 1.0) * 0.8
    else:
        strength = 0.5 + (vol_ratio - 1.0) * 0.2
    return {
        "strength": _clamp(strength),
        "volume_ratio": vol_ratio,
        "return_5d": ret_5,
    }

def _compute_multi_index_volume(index_frames: Dict[str, Any]) -> tuple[float, Dict[str, float]]:
    weighted = 0.0
    total_weight = 0.0
    detail: Dict[str, float] = {}

    for symbol, _label, weight in _regime_indexes():
        metrics = _index_volume_confirmation(index_frames.get(symbol))
        if not metrics:
            continue
        weighted += metrics["strength"] * weight
        total_weight += weight
        detail[f"volume_ratio_{symbol}"] = round(metrics["volume_ratio"], 4)
        detail[f"volume_ret5_{symbol}"] = round(metrics["return_5d"], 4)

    if total_weight <= 0:
        return 0.5, detail
    return weighted / total_weight, detail

def _compute_volume_strength(
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
    market_volume: MarketVolume,
) -> tuple[float, str, Dict[str, float]]:
    try:
        det_cfg = _load_config()["adaptive"]["detection"]
        vol_expand = float(det_cfg.get("volume_expansion", 1.2))
        vol_contract = float(det_cfg.get("volume_contraction", 0.8))
    except Exception:
        vol_expand = 1.2
        vol_contract = 0.8

    index_volume, index_detail = _compute_multi_index_volume(index_frames)
    return _score_volume_strength(
        amount_ratio_5_20=market_volume.amount_ratio_5_20,
        advance_ratio=breadth.advance_ratio,
        up_amount_ratio=market_volume.up_amount_ratio,
        index_volume=index_volume,
        sample_size=market_volume.sample_size,
        amount_5d=market_volume.amount_5d,
        amount_20d=market_volume.amount_20d,
        volume_expansion=vol_expand,
        volume_contraction=vol_contract,
        index_detail=index_detail,
    )
