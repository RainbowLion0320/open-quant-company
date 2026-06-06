"""Portfolio sector exposure snapshot builder."""
from __future__ import annotations

import json
from datetime import date

import pandas as pd

from data.storage.datahub import DataHub
from data.market.sector_pipeline.membership import _snapshot_path


def build_exposure(hub: DataHub | None = None) -> pd.DataFrame:
    """Aggregate Paper/Portfolio positions by sector exposure."""
    hub = hub or DataHub()

    pos_df = _load_position_snapshot(hub)
    if pos_df.empty or "symbol" not in pos_df.columns:
        return pd.DataFrame()

    mem_path = hub.dimension_path("sector_membership")
    mem = hub.read_parquet(mem_path, default=pd.DataFrame()) if mem_path.exists() else pd.DataFrame()
    if mem.empty:
        return pd.DataFrame()

    sym_to_sector = dict(zip(mem["symbol"], mem["sector_name"]))
    total_value = float(pos_df["market_value"].sum()) if "market_value" in pos_df.columns else 0.0
    today = date.today().isoformat()
    sector_groups: dict[str, dict] = {}

    for _, row_data in pos_df.iterrows():
        symbol = str(row_data.get("symbol", ""))
        sector = sym_to_sector.get(symbol, "待分类")
        mv = float(row_data.get("market_value", 0))
        sector_groups.setdefault(sector, {"market_value": 0.0, "count": 0})
        sector_groups[sector]["market_value"] += mv
        sector_groups[sector]["count"] += 1

    df = pd.DataFrame([
        {
            "sector": sector,
            "date": today,
            "weight": round(stats["market_value"] / max(total_value, 1), 4),
            "market_value": round(stats["market_value"], 2),
            "position_count": stats["count"],
        }
        for sector, stats in sector_groups.items()
    ])
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
