"""
Sector / Industry data pipeline — membership, performance, signal aggregation.

P2: Builds snapshots consumed by the Sector Radar Web UI.
All computation reads from local parquet caches; no live API calls.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path
from datetime import date

from data.datahub import DataHub


# ── 申万一级行业 ──

SW_INDUSTRIES: dict[str, str] = {
    "801010": "农林牧渔", "801030": "基础化工",  "801040": "钢铁",
    "801050": "有色金属", "801080": "电子",      "801110": "家用电器",
    "801120": "食品饮料", "801130": "纺织服饰",  "801140": "轻工制造",
    "801150": "医药生物", "801160": "公用事业",  "801170": "交通运输",
    "801180": "房地产",   "801200": "商贸零售",  "801210": "社会服务",
    "801230": "综合",     "801710": "建筑材料",  "801720": "建筑装饰",
    "801730": "电力设备", "801740": "国防军工",  "801750": "计算机",
    "801760": "传媒",     "801770": "通信",      "801780": "银行",
    "801790": "非银金融", "801880": "汽车",      "801890": "机械设备",
    "801950": "石油石化", "801960": "煤炭",      "801970": "环保",
    "801980": "美容护理",
}


_LEGACY_SW_ALIASES: dict[str, str] = {
    "采掘": "煤炭",
    "化工": "基础化工",
    "纺织服装": "纺织服饰",
    "休闲服务": "社会服务",
}


def _store(hub: DataHub | None = None) -> Path:
    """Compatibility helper: sector store under the active DataHub."""
    hub = hub or DataHub()
    store = hub.store_path("sector")
    store.mkdir(parents=True, exist_ok=True)
    return store


def _snapshot_path(hub: DataHub, dimension: str, run_date: date) -> Path:
    return hub.dimension_path(dimension, YYYYMMDD=run_date.strftime("%Y%m%d"))


def _canonical_sector_name(name: str) -> str:
    return _LEGACY_SW_ALIASES.get(str(name).strip(), str(name).strip())


def _period_return(returns: pd.Series, days: int) -> float:
    if len(returns) < days:
        return 0.0
    window = pd.to_numeric(returns.tail(days), errors="coerce").dropna()
    if window.empty:
        return 0.0
    return float((1.0 + window).prod() - 1.0)


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


# ═══════════════════════════════════════
# Membership
# ═══════════════════════════════════════

def build_membership(hub: DataHub | None = None) -> pd.DataFrame:
    """Build stock→sector membership from known symbol lists.

    Returns DataFrame with columns: symbol, sector_code, sector_name, sector_level
    """
    if hub is None:
        hub = DataHub()

    from data.symbols import SYMBOL_INDUSTRY

    name_to_code = {name: code for code, name in SW_INDUSTRIES.items()}
    rows = []
    for symbol, industry in SYMBOL_INDUSTRY.items():
        if not industry or industry == "待分类":
            continue
        sector_name = _canonical_sector_name(industry)
        sector_code = name_to_code.get(sector_name, "")
        if not sector_code:
            continue
        rows.append({
            "symbol": symbol,
            "sector_code": sector_code,
            "sector_name": sector_name,
            "sector_level": 1,
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        path = hub.dimension_path("sector_membership")
        hub.write_parquet(df, path, producer="sectors.build_membership")
    return df


# ═══════════════════════════════════════
# Sector Performance (from member stocks)
# ═══════════════════════════════════════

def build_sector_performance(
    hub: DataHub | None = None,
    lookback_days: int = 120,
) -> pd.DataFrame:
    """Build sector-level performance from cached SW index data or stock proxy.

    The preferred input is ``sector_sw_daily``.  When that cache is absent, the
    builder falls back to equal-weighted member stock returns and explicitly
    labels the result as ``data_source=proxy``.
    """
    if hub is None:
        hub = DataHub()

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
            df["amount_share"] = (pd.to_numeric(df["amount_5d_avg"], errors="coerce").fillna(0).clip(lower=0) / total_amount).round(4)
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
        dates = _normalize_date_series(df)
        work = df.copy()
        work["_date"] = dates
        sort_col = "trade_date" if "trade_date" in work.columns else "_date"
        work = work.sort_values(sort_col).tail(lookback_days)
        returns = _normalize_return_series(work).dropna()
        if returns.empty:
            continue
        latest_date = str(work["_date"].iloc[-1])[:10]
        return returns.reset_index(drop=True), latest_date, "real", len(work), _amount_metrics(work, source="real")
    return pd.Series(dtype="float64"), "", "missing", 0, _empty_amount_metrics()


def _build_proxy_returns(
    hub: DataHub,
    symbols: list[str],
    lookback_days: int,
) -> tuple[pd.Series, str, int, dict]:
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
        dates = _normalize_date_series(df)
        work = df.copy()
        work["_date"] = dates
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

    if "_date" in df.columns:
        index = df["_date"]
    else:
        index = _normalize_date_series(df)

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


# ═══════════════════════════════════════
# Signal Aggregation
# ═══════════════════════════════════════

def build_signal_aggregation(hub: DataHub | None = None) -> pd.DataFrame:
    """Aggregate strategy signals by sector.

    Reads each strategy's signal parquet, maps stocks→sectors,
    and computes buy_ratio/avg_score/top_symbol per sector.
    """
    if hub is None:
        hub = DataHub()

    mem_path = hub.dimension_path("sector_membership")
    if not mem_path.exists():
        return pd.DataFrame()

    mem = hub.read_parquet(mem_path, default=pd.DataFrame())
    if mem.empty:
        return pd.DataFrame()

    today = date.today().isoformat()
    rows = []

    for strategy in ("buffett", "multifactor", "cybernetic", "ml_lgbm"):
        sig_path = hub.signal_path(strategy)
        if not sig_path.exists():
            continue

        sig_df = hub.read_parquet(sig_path, default=pd.DataFrame())
        if sig_df.empty:
            continue

        sym_to_sector = dict(zip(mem["symbol"], mem["sector_name"]))
        name_to_code = dict(zip(mem["sector_name"], mem["sector_code"]))
        sector_stats: dict[str, dict] = {}

        for _, row_data in sig_df.iterrows():
            symbol = str(row_data.get("symbol", ""))
            sector = sym_to_sector.get(symbol, "")
            if not sector:
                continue

            if sector not in sector_stats:
                sector_stats[sector] = {"total": 0, "buys": 0, "scores": [], "best": ("", 0)}
            s = sector_stats[sector]
            s["total"] += 1
            score = float(row_data.get("score", 0))
            s["scores"].append(score)
            signal = str(row_data.get("signal", "")).lower()
            if signal == "buy":
                s["buys"] += 1
            if score > s["best"][1]:
                s["best"] = (symbol, score)

        for sector_name, stats in sector_stats.items():
            rows.append({
                "sector": sector_name,
                "sector_code": name_to_code.get(sector_name, ""),
                "date": today,
                "strategy": strategy,
                "total": stats["total"],
                "buy_count": stats["buys"],
                "buy_ratio": round(stats["buys"] / max(stats["total"], 1), 4),
                "avg_score": round(np.mean(stats["scores"]), 2),
                "top_symbol": stats["best"][0],
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        dest = _snapshot_path(hub, "sector_signal_snapshot", date.today())
        hub.write_parquet(df, dest, producer="sectors.build_signal_aggregation")
    return df


# ═══════════════════════════════════════
# Portfolio Exposure
# ═══════════════════════════════════════

def build_exposure(hub: DataHub | None = None) -> pd.DataFrame:
    """Aggregate Paper/Portfolio positions by sector exposure.

    Returns DataFrame with columns: sector, date, weight, market_value, position_count
    """
    if hub is None:
        hub = DataHub()

    pos_df = _load_position_snapshot(hub)
    if pos_df.empty or "symbol" not in pos_df.columns:
        return pd.DataFrame()

    # Load membership
    mem_path = hub.dimension_path("sector_membership")
    mem = hub.read_parquet(mem_path, default=pd.DataFrame()) if mem_path.exists() else pd.DataFrame()

    if mem.empty:
        return pd.DataFrame()

    sym_to_sector = dict(zip(mem["symbol"], mem["sector_name"]))

    total_value = float(pos_df["market_value"].sum()) if "market_value" in pos_df.columns else 0.0
    today = date.today().isoformat()
    rows = []

    sector_groups: dict[str, dict] = {}
    for _, row_data in pos_df.iterrows():
        symbol = str(row_data.get("symbol", ""))
        sector = sym_to_sector.get(symbol, "待分类")
        mv = float(row_data.get("market_value", 0))
        if sector not in sector_groups:
            sector_groups[sector] = {"market_value": 0.0, "count": 0}
        sector_groups[sector]["market_value"] += mv
        sector_groups[sector]["count"] += 1

    for sector, stats in sector_groups.items():
        rows.append({
            "sector": sector,
            "date": today,
            "weight": round(stats["market_value"] / max(total_value, 1), 4),
            "market_value": round(stats["market_value"], 2),
            "position_count": stats["count"],
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        dest = _snapshot_path(hub, "sector_exposure_snapshot", date.today())
        hub.write_parquet(df, dest, producer="sectors.build_exposure")
    return df


def _load_position_snapshot(hub: DataHub) -> pd.DataFrame:
    """Load positions from canonical paper state."""
    state_path = hub.paper_path("state")
    if not state_path.exists():
        return pd.DataFrame()

    state = hub.read_parquet(state_path, default=pd.DataFrame())
    if state.empty or "positions" not in state.columns:
        return pd.DataFrame()

    raw_positions = state.iloc[0].get("positions", {})
    if isinstance(raw_positions, str):
        try:
            import json
            raw_positions = json.loads(raw_positions)
        except Exception:
            raw_positions = {}
    if not isinstance(raw_positions, dict) or not raw_positions:
        return pd.DataFrame()

    rows = []
    for symbol, pos in raw_positions.items():
        if not isinstance(pos, dict):
            continue
        volume = float(pos.get("volume", 0) or 0)
        avg_cost = float(pos.get("avg_cost", 0) or 0)
        market_value = pos.get("market_value")
        if market_value is None or pd.isna(market_value):
            market_value = _latest_market_value(hub, str(symbol), volume, avg_cost)
        rows.append({
            "symbol": str(symbol),
            "market_value": float(market_value or 0),
            "volume": volume,
            "avg_cost": avg_cost,
            "name": str(pos.get("name", "")),
        })
    return pd.DataFrame(rows)


def _latest_market_value(hub: DataHub, symbol: str, volume: float, avg_cost: float) -> float:
    try:
        ohlcv_path = hub.dimension_path("ohlcv_daily", symbol=symbol)
        if ohlcv_path.exists():
            df = hub.read_parquet(ohlcv_path, default=pd.DataFrame())
            if not df.empty and "close" in df.columns:
                price = float(pd.to_numeric(df["close"], errors="coerce").dropna().iloc[-1])
                return volume * price
    except Exception:
        pass
    return volume * avg_cost


# ═══════════════════════════════════════
# Orchestrator
# ═══════════════════════════════════════

def build_all(hub: DataHub | None = None) -> dict:
    """Run all sector snapshot builders. Returns summary dict."""
    if hub is None:
        hub = DataHub()

    results = {}

    for name, builder in [
        ("membership", build_membership),
        ("performance", build_sector_performance),
        ("signals", build_signal_aggregation),
        ("exposure", build_exposure),
    ]:
        try:
            df = builder(hub)
            results[name] = {"status": "ok", "rows": len(df)}
        except Exception as e:
            results[name] = {"status": "error", "message": str(e)[:200]}

    return results


def _empty_sector_row(code: str, name: str, today: date) -> dict:
    return {
        "sector_code": code,
        "sector_name": name,
        "date": today.isoformat(),
        "return_1d": 0.0, "return_5d": 0.0, "return_20d": 0.0, "return_60d": 0.0,
        "volatility": 0.0, "member_count": 0, "turnover_amount": 0.0,
        "amount_5d_avg": 0.0, "amount_share": 0.0, "amount_source": "missing", "latest_date": "",
        "data_source": "missing",
    }
