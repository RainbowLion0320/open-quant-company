"""Market observation, breadth/volume, scoring, and HMM feature helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence
import math
import os
import time

from cybernetics.config import _detection_config, _load_config
from cybernetics.regime import MarketRegime
from cybernetics.regime_policy import PRODUCTION_REGIME_POLICY
from cybernetics.regime_scoring import (
    breadth_strength as _score_breadth_strength,
    classify_regime_value,
    clamp as _score_clamp,
    compose_regime_score,
    volume_strength as _score_volume_strength,
)
from cybernetics.types import MarketBreadth, MarketVolume


# =====================================================================
# 3. 自适应机制 (Adaptive)
# =====================================================================

_BREADTH_CACHE: Dict[str, Any] = {"expires_at": 0.0, "snapshot": None}
_VOLUME_CACHE: Dict[str, Any] = {"expires_at": 0.0, "snapshot": None}
_REGIME_TRACKER: Optional[RegimeTransitionTracker] = None
_REGIME_TRACKER_PATH: Optional[str] = None

def _get_regime_indexes() -> list[tuple]:
    """Read regime index weights from config, fallback to defaults."""
    from core.settings import get_section
    cfg = get_section("cybernetics.regime_indexes", {}) or {}
    _INDEX_NAMES = {
        "sh000001": "上证综指", "sh000300": "沪深300",
        "sz399001": "深证成指", "sz399006": "创业板指", "sh000905": "中证500",
    }
    defaults = {"sh000001": 0.25, "sh000300": 0.25, "sz399001": 0.20, "sz399006": 0.15, "sh000905": 0.15}
    merged = {**defaults, **cfg}
    return [(k, _INDEX_NAMES.get(k, k), v) for k, v in merged.items()]


# Kept for compatibility with older tests/imports; current config is read on
# each detection so Config Center changes apply without restarting the API.
_REGIME_INDEXES: list[tuple] | None = None


def _regime_indexes() -> list[tuple]:
    return _get_regime_indexes()


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return _score_clamp(value, lower, upper)


def _frame_close_volume(df):
    """Return a sorted OHLCV-like frame with numeric close/volume columns."""
    import pandas as pd

    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["date", "close", "volume"])

    data = df.copy()
    data.columns = [str(c).lower() for c in data.columns]
    if "close" not in data.columns and "收盘" in df.columns:
        data["close"] = df["收盘"]
    if "volume" not in data.columns and "成交量" in df.columns:
        data["volume"] = df["成交量"]

    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data = data.dropna(subset=["date"]).sort_values("date")
    elif data.index.name:
        data = data.reset_index().rename(columns={data.index.name: "date"})
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data = data.dropna(subset=["date"]).sort_values("date")

    data["close"] = pd.to_numeric(data.get("close"), errors="coerce")
    if "volume" in data.columns:
        data["volume"] = pd.to_numeric(data["volume"], errors="coerce")
    return data.dropna(subset=["close"]).reset_index(drop=True)


def _stock_daily_files() -> list:
    from data.datahub import get_datahub

    daily_dir = get_datahub().store_path("stock") / "daily"
    if not daily_dir.exists():
        return []
    return sorted(daily_dir.glob("*.parquet"))


def _stock_daily_source_sql(files: Optional[Sequence[Any]] = None) -> Optional[str]:
    if files is None:
        from data.datahub import get_datahub

        daily_dir = get_datahub().store_path("stock") / "daily"
        if not daily_dir.exists():
            return None
        return "'" + str(daily_dir / "*.parquet").replace("'", "''") + "'"

    paths = [str(path).replace("'", "''") for path in files]
    if not paths:
        return None
    return "[" + ", ".join(f"'{path}'" for path in paths) + "]"


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


def _index_trend_strength(df) -> Optional[float]:
    data = _frame_close_volume(df)
    if len(data) < 60:
        return None

    close = data["close"]
    current = float(close.iloc[-1])
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean())
    ma120 = float(close.tail(120).mean()) if len(close) >= 120 else ma60

    checks = [
        current > ma20,
        current > ma60,
        ma20 > ma60,
        current > ma120,
    ]
    if len(close) >= 80:
        prev_ma20 = float(close.iloc[-40:-20].mean())
        checks.append(ma20 > prev_ma20)

    return sum(1 for ok in checks if ok) / len(checks)


def _compute_multi_index_trend(index_frames: Dict[str, Any]) -> tuple[float, Dict[str, float]]:
    weighted = 0.0
    total_weight = 0.0
    detail: Dict[str, float] = {}

    for symbol, _label, weight in _regime_indexes():
        strength = _index_trend_strength(index_frames.get(symbol))
        if strength is None:
            continue
        detail[symbol] = round(strength, 4)
        weighted += strength * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.5, detail
    return weighted / total_weight, detail


def _index_risk_metrics(df) -> Optional[Dict[str, float]]:
    data = _frame_close_volume(df)
    if len(data) < 30:
        return None

    close = data["close"]
    returns = close.pct_change().dropna()
    if len(returns) < 10:
        realized_vol = 0.0
    else:
        realized_vol = float(returns.tail(20).std() * math.sqrt(252))
        if not math.isfinite(realized_vol):
            realized_vol = 0.0

    window = close.tail(60)
    peak = float(window.max())
    current = float(close.iloc[-1])
    drawdown = (current / peak - 1.0) if peak > 0 else 0.0

    vol_score = 1.0 - _clamp((realized_vol - 0.12) / 0.28)
    drawdown_score = 1.0 - _clamp(abs(min(drawdown, 0.0)) / 0.15)
    return {
        "realized_vol_20d": realized_vol,
        "drawdown_60d": drawdown,
        "vol_score": vol_score,
        "drawdown_score": drawdown_score,
    }


def _compute_risk_strength(
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
) -> tuple[float, Dict[str, float]]:
    try:
        risk_weights = (_load_config().get("risk_strength_weights", {}) or {})
    except Exception:
        risk_weights = {}
    drawdown_weight = float(risk_weights.get("drawdown", 0.50))
    volatility_weight = float(risk_weights.get("volatility", 0.30))
    pressure_weight = float(risk_weights.get("pressure", 0.20))
    total_component_weight = drawdown_weight + volatility_weight + pressure_weight
    if total_component_weight <= 0:
        drawdown_weight, volatility_weight, pressure_weight = 0.50, 0.30, 0.20
        total_component_weight = 1.0
    drawdown_weight /= total_component_weight
    volatility_weight /= total_component_weight
    pressure_weight /= total_component_weight

    weighted_vol_score = 0.0
    weighted_drawdown_score = 0.0
    weighted_realized_vol = 0.0
    weighted_drawdown = 0.0
    total_weight = 0.0
    worst_drawdown = 0.0
    index_detail: Dict[str, float] = {}

    for symbol, _label, weight in _regime_indexes():
        metrics = _index_risk_metrics(index_frames.get(symbol))
        if not metrics:
            continue
        weighted_vol_score += metrics["vol_score"] * weight
        weighted_drawdown_score += metrics["drawdown_score"] * weight
        weighted_realized_vol += metrics["realized_vol_20d"] * weight
        weighted_drawdown += metrics["drawdown_60d"] * weight
        worst_drawdown = min(worst_drawdown, metrics["drawdown_60d"])
        index_detail[f"risk_vol_{symbol}"] = round(metrics["realized_vol_20d"], 4)
        index_detail[f"risk_drawdown_{symbol}"] = round(metrics["drawdown_60d"], 4)
        total_weight += weight

    if total_weight <= 0:
        vol_health = 0.5
        drawdown_health = 0.5
        weighted_realized_vol = 0.0
        weighted_drawdown = 0.0
    else:
        vol_health = weighted_vol_score / total_weight
        drawdown_health = weighted_drawdown_score / total_weight
        weighted_realized_vol = weighted_realized_vol / total_weight
        weighted_drawdown = weighted_drawdown / total_weight

    traded = breadth.up_count + breadth.down_count + breadth.unchanged_count
    down_ratio = (breadth.down_count / traded) if traded else 0.5
    pressure_raw = (
        0.50 * down_ratio
        + 0.30 * (1.0 - breadth.above_ma20)
        + 0.20 * (1.0 - breadth.above_ma60)
    )
    pressure_health = 1.0 - _clamp((pressure_raw - 0.40) / 0.35)

    strength = (
        drawdown_weight * drawdown_health
        + volatility_weight * vol_health
        + pressure_weight * pressure_health
    )
    return strength, {
        "risk_drawdown_raw": round(drawdown_health, 4),
        "risk_volatility_raw": round(vol_health, 4),
        "risk_pressure_raw": round(pressure_health, 4),
        "risk_drawdown_weight": round(drawdown_weight, 4),
        "risk_volatility_weight": round(volatility_weight, 4),
        "risk_pressure_weight": round(pressure_weight, 4),
        "market_down_pressure": round(pressure_raw, 4),
        "market_down_ratio": round(down_ratio, 4),
        "realized_vol_20d": round(weighted_realized_vol, 4),
        "drawdown_60d": round(weighted_drawdown, 4),
        "worst_drawdown_60d": round(worst_drawdown, 4),
        **index_detail,
    }


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


def _breadth_strength(breadth: MarketBreadth) -> float:
    return _score_breadth_strength(
        breadth.advance_ratio,
        breadth.above_ma20,
        breadth.above_ma60,
        breadth.above_ma120,
    )


def _compute_regime_score_v2(
    bench_df,
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
    market_volume: Optional[MarketVolume] = None,
) -> tuple[float, Dict[str, float]]:
    """Compute validated regime score using configured component weights."""
    trend_raw, index_trend = _compute_multi_index_trend(index_frames)
    risk_raw, risk_detail = _compute_risk_strength(index_frames, breadth)
    volume_snapshot = market_volume or _compute_full_market_volume()
    volume_raw, _volume_trend, volume_detail = _compute_volume_strength(index_frames, breadth, volume_snapshot)
    breadth_raw = _breadth_strength(breadth)

    return compose_regime_score(
        trend_raw=trend_raw,
        breadth_raw=breadth_raw,
        risk_raw=risk_raw,
        volume_raw=volume_raw,
        sample_size=breadth.sample_size,
        index_trend=index_trend,
        risk_detail=risk_detail,
        volume_detail=volume_detail,
    )


def _classify_regime(score: float, components: Dict[str, float], breadth: MarketBreadth) -> MarketRegime:
    try:
        det_cfg = _detection_config()
        bull_threshold = float(det_cfg.get("regime_bull_threshold", PRODUCTION_REGIME_POLICY.bull_threshold))
        bear_threshold = float(det_cfg.get("regime_bear_threshold", PRODUCTION_REGIME_POLICY.bear_threshold))
        trend_bull = float(det_cfg.get("regime_trend_confirm", PRODUCTION_REGIME_POLICY.trend_confirm))
        trend_bear = float(det_cfg.get("regime_bear_trend_breakdown", PRODUCTION_REGIME_POLICY.bear_trend_breakdown))
        breadth_bull = float(det_cfg.get("breadth_bull_threshold", PRODUCTION_REGIME_POLICY.breadth_confirm))
        breadth_bear = float(det_cfg.get("breadth_bear_threshold", PRODUCTION_REGIME_POLICY.bear_breadth_breakdown))
    except Exception:
        bull_threshold = PRODUCTION_REGIME_POLICY.bull_threshold
        bear_threshold = PRODUCTION_REGIME_POLICY.bear_threshold
        trend_bull = PRODUCTION_REGIME_POLICY.trend_confirm
        trend_bear = PRODUCTION_REGIME_POLICY.bear_trend_breakdown
        breadth_bull = PRODUCTION_REGIME_POLICY.breadth_confirm
        breadth_bear = PRODUCTION_REGIME_POLICY.bear_breadth_breakdown

    trend_raw = components.get("trend_raw", 0.5)
    breadth_raw = components.get("breadth_raw", _breadth_strength(breadth))

    return MarketRegime(
        classify_regime_value(
            score,
            trend_raw=trend_raw,
            breadth_raw=breadth_raw,
            advance_ratio=breadth.advance_ratio,
            bull_threshold=bull_threshold,
            bear_threshold=bear_threshold,
            trend_bull=trend_bull,
            trend_bear=trend_bear,
            breadth_bull=breadth_bull,
            breadth_bear=breadth_bear,
        )
    )


def _hmm_detect(
    index_frames: Dict[str, Any],
    breadth: MarketBreadth,
    volume: MarketVolume,
) -> tuple[Dict[str, float], float, float, MarketRegime]:
    """Run Student-t HMM regime detection.

    Returns (regime_probs, confidence, entropy, raw_regime).
    Raises if model not available or inference fails.
    """
    import math

    import numpy as np

    from cybernetics.features import OBSERVATION_COLUMNS, build_observation_matrix, build_regime_features
    from cybernetics.hmm_engine import StudentTHMM, apply_hmm_preprocessor, load_hmm_model

    # Check model path
    try:
        hmm_cfg = _load_config().get("hmm", {})
        model_path = hmm_cfg.get("model_path", "data/models/regime_hmm")
    except Exception:
        model_path = "data/models/regime_hmm"

    from pathlib import Path
    mp = Path(model_path)
    if not (mp / "params.npz").exists():
        raise FileNotFoundError(f"HMM model not found at {mp}")

    # Build features
    # Load bond returns for stock-bond correlation feature
    from cybernetics.features import load_bond_returns
    bond_ret = load_bond_returns()

    features = build_regime_features(
        index_frames,
        breadth_raw=_score_breadth_strength(
            breadth.advance_ratio, breadth.above_ma20, breadth.above_ma60, breadth.above_ma120
        ),
        breadth_above_ma20=breadth.above_ma20,
        breadth_above_ma60=breadth.above_ma60,
        breadth_above_ma120=breadth.above_ma120,
        amount_ratio_5_20=volume.amount_ratio_5_20,
        advance_ratio=breadth.advance_ratio,
        up_amount_ratio=volume.up_amount_ratio,
        sample_size=breadth.sample_size,
        bond_returns=bond_ret,
    )
    if features.empty:
        raise ValueError("Feature construction returned empty DataFrame")

    # Load model
    result = load_hmm_model(mp)

    # Build observation for latest day
    obs_cols = hmm_cfg.get("observation_columns", OBSERVATION_COLUMNS)
    obs, _pca = build_observation_matrix(features, columns=obs_cols, standardise=True)
    if len(obs) == 0:
        raise ValueError("Observation matrix is empty")

    # Use the last observation
    latest = obs[-1:]  # (1, D)
    latest = apply_hmm_preprocessor(latest, result.preprocessor)
    if latest.shape[1] != result.n_features:
        raise ValueError(f"HMM model expects {result.n_features} features, got {latest.shape[1]}")

    # Predict probabilities
    hmm = StudentTHMM(result.config)
    hmm._params = {
        "means": result.means,
        "covars": result.covars,
        "df": result.df,
        "transmat": result.transmat,
        "startprob": result.startprob,
    }
    probs = hmm.predict_proba(latest)[0]  # (3,)

    # Map to regime labels (aligned: 0=bull, 1=sideways, 2=bear)
    regime_probs = {
        "bull": float(probs[0]),
        "sideways": float(probs[1]),
        "bear": float(probs[2]),
    }
    confidence = float(max(probs))
    entropy = -sum(p * math.log(p + 1e-300) for p in probs)

    # Argmax regime
    regime_idx = int(np.argmax(probs))
    regime_map = {0: MarketRegime.BULL, 1: MarketRegime.SIDEWAYS, 2: MarketRegime.BEAR}
    raw_regime = regime_map.get(regime_idx, MarketRegime.SIDEWAYS)

    return regime_probs, confidence, entropy, raw_regime
