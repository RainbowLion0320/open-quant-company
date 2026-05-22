"""
Sector / Industry data pipeline — membership, performance, signal aggregation.

P2: Builds snapshots consumed by the Sector Radar Web UI.
All computation reads from local parquet caches; no live API calls.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from data.datahub import DataHub
from data.data_registry import get_registry


# ── 申万一级行业 ──

SW_INDUSTRIES: dict[str, str] = {
    "801010": "农林牧渔", "801020": "采掘",      "801030": "化工",
    "801040": "钢铁",     "801050": "有色金属",  "801080": "电子",
    "801110": "家用电器", "801120": "食品饮料",  "801130": "纺织服装",
    "801140": "轻工制造", "801150": "医药生物",  "801160": "公用事业",
    "801170": "交通运输", "801180": "房地产",    "801200": "商贸零售",
    "801210": "休闲服务", "801230": "综合",      "801710": "建筑材料",
    "801720": "建筑装饰", "801730": "电力设备",  "801740": "国防军工",
    "801750": "计算机",   "801760": "传媒",      "801770": "通信",
    "801880": "汽车",     "801890": "机械设备",
    "801970": "银行",     "801980": "非银金融",
}


def _store() -> Path:
    store = Path(__file__).resolve().parent / "store" / "sector"
    store.mkdir(parents=True, exist_ok=True)
    return store


# ═══════════════════════════════════════
# Membership
# ═══════════════════════════════════════

def build_membership(hub: DataHub | None = None) -> pd.DataFrame:
    """Build stock→sector membership from known symbol lists.

    Returns DataFrame with columns: symbol, sector_code, sector_name, sector_level
    """
    if hub is None:
        hub = DataHub()

    from data.symbols import SYMBOL_INDUSTRY, StockUniverse

    universe = StockUniverse()
    rows = []
    for symbol, industry in SYMBOL_INDUSTRY.items():
        if not industry or industry == "待分类":
            continue
        # Find sector code by name
        sector_code = ""
        for code, name in SW_INDUSTRIES.items():
            if name == industry:
                sector_code = code
                break
        if not sector_code:
            continue
        rows.append({
            "symbol": symbol,
            "sector_code": sector_code,
            "sector_name": industry,
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
    """Aggregate member stock returns to compute sector-level performance.

    Uses the membership table and individual stock OHLCV data.
    Falls back to empty DataFrame if OHLCV data is missing.
    """
    if hub is None:
        hub = DataHub()

    # Load membership
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
        if not sector_symbols:
            rows.append(_empty_sector_row(sector_code, sector_name, today))
            continue

        sector_returns = []
        symbol_count = 0
        latest_date = ""
        for symbol in sector_symbols[:100]:  # cap per sector for performance
            ohlcv_path = hub.dimension_path("ohlcv_daily", symbol=symbol)
            if not ohlcv_path.exists():
                continue
            df = hub.read_parquet(ohlcv_path, default=pd.DataFrame())
            if df.empty or "close" not in df.columns:
                continue
            df = df.sort_values("date")
            if "return_1d" not in df.columns and "close" in df.columns:
                df["return_1d"] = df["close"].pct_change()
            # Use most recent N days
            recent = df.tail(lookback_days)
            if recent.empty:
                continue
            sector_returns.append(recent.set_index("date")["return_1d"])
            symbol_count += 1
            if not latest_date or str(recent["date"].iloc[-1]) > latest_date:
                latest_date = str(recent["date"].iloc[-1])[:10]

        if not sector_returns:
            rows.append(_empty_sector_row(sector_code, sector_name, today))
            continue

        # Equal-weighted sector return
        ret_df = pd.concat(sector_returns, axis=1)
        sector_ret = ret_df.mean(axis=1).dropna()

        # Volatility
        sector_vol = sector_ret.std() * np.sqrt(252) if len(sector_ret) > 1 else 0.0

        # Momentum windows
        ret_1d = float(sector_ret.iloc[-1]) if len(sector_ret) > 0 else 0.0
        ret_5d = float(sector_ret.iloc[-5:].sum()) if len(sector_ret) >= 5 else 0.0
        ret_20d = float(sector_ret.iloc[-20:].sum()) if len(sector_ret) >= 20 else 0.0
        ret_60d = float(sector_ret.iloc[-60:].sum()) if len(sector_ret) >= 60 else 0.0

        rows.append({
            "sector_code": sector_code,
            "sector_name": sector_name,
            "date": today.isoformat(),
            "return_1d": round(ret_1d, 6),
            "return_5d": round(ret_5d, 6),
            "return_20d": round(ret_20d, 6),
            "return_60d": round(ret_60d, 6),
            "volatility": round(sector_vol, 4),
            "member_count": symbol_count,
            "latest_date": latest_date,
            "data_source": "real" if symbol_count > 0 else "missing",
        })

    df = pd.DataFrame(rows)
    if not df.empty:
        dest = _store() / f"sector_performance_{today.isoformat()}.parquet"
        hub.write_parquet(df, dest, producer="sectors.build_performance")
    return df


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
        dest = _store() / f"sector_signals_{today}.parquet"
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

    # Load positions
    pos_path = hub.store_root / "paper" / "positions.parquet"
    if not pos_path.exists():
        return pd.DataFrame()

    pos_df = hub.read_parquet(pos_path, default=pd.DataFrame())
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
        dest = _store() / f"sector_exposure_{today}.parquet"
        hub.write_parquet(df, dest, producer="sectors.build_exposure")
    return df


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
        "volatility": 0.0, "member_count": 0, "latest_date": "",
        "data_source": "missing",
    }
