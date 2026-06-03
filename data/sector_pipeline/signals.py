"""Sector-level strategy signal aggregation."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from data.datahub import DataHub
from data.sector_pipeline.membership import _snapshot_path


def build_signal_aggregation(hub: DataHub | None = None) -> pd.DataFrame:
    """Aggregate strategy signals by sector."""
    hub = hub or DataHub()

    mem_path = hub.dimension_path("sector_membership")
    if not mem_path.exists():
        return pd.DataFrame()

    mem = hub.read_parquet(mem_path, default=pd.DataFrame())
    if mem.empty:
        return pd.DataFrame()

    today = date.today().isoformat()
    rows = []
    sym_to_sector = dict(zip(mem["symbol"], mem["sector_name"]))
    name_to_code = dict(zip(mem["sector_name"], mem["sector_code"]))

    for strategy in ("buffett", "multifactor", "cybernetic", "ml_lgbm"):
        sig_path = hub.signal_path(strategy)
        if not sig_path.exists():
            continue

        sig_df = hub.read_parquet(sig_path, default=pd.DataFrame())
        if sig_df.empty:
            continue

        sector_stats: dict[str, dict] = {}
        for _, row_data in sig_df.iterrows():
            symbol = str(row_data.get("symbol", ""))
            sector = sym_to_sector.get(symbol, "")
            if not sector:
                continue

            if sector not in sector_stats:
                sector_stats[sector] = {"total": 0, "buys": 0, "scores": [], "best": ("", 0)}
            stat = sector_stats[sector]
            stat["total"] += 1
            score = float(row_data.get("score", 0))
            stat["scores"].append(score)
            if str(row_data.get("signal", "")).lower() == "buy":
                stat["buys"] += 1
            if score > stat["best"][1]:
                stat["best"] = (symbol, score)

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
