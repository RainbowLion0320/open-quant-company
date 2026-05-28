"""Sector API domain service."""

from __future__ import annotations

import pandas as pd

from data.datahub import get_datahub
from web.api.serializers import safe_float, safe_int

HUB = get_datahub()


def source_summary(sectors: list[dict]) -> str:
    sources = {str(s.get("data_source", "missing")) for s in sectors}
    if "real" in sources:
        return "real"
    if "proxy" in sources:
        return "proxy"
    return "missing"


def capital_source_summary(sectors: list[dict]) -> str:
    sources = {str(s.get("amount_source", "missing")) for s in sectors}
    if "real" in sources:
        return "real"
    if "proxy" in sources:
        return "proxy"
    if "estimated" in sources:
        return "estimated"
    return "missing"


def _read_snapshot(dimension: str):
    path = HUB.latest_dimension_snapshot(dimension)
    if not path:
        return None, pd.DataFrame()
    return path, HUB.read_parquet(path, default=pd.DataFrame())


def _signal_map(sigs: pd.DataFrame, sector_name: str) -> dict:
    if sigs.empty:
        return {}
    result = {}
    for _, row in sigs[sigs["sector"] == sector_name].iterrows():
        strategy = str(row.get("strategy", ""))
        result[strategy] = {
            "total": safe_int(row.get("total", 0)),
            "buy_count": safe_int(row.get("buy_count", 0)),
            "buy_ratio": safe_float(row.get("buy_ratio", 0)),
            "avg_score": safe_float(row.get("avg_score", 0)),
            "top_symbol": str(row.get("top_symbol", "")),
        }
    return result


def build_sector_overview() -> dict:
    perf_path, perf = _read_snapshot("sector_performance_snapshot")
    sig_path, sigs = _read_snapshot("sector_signal_snapshot")

    sectors = []
    if not perf.empty:
        perf = perf.sort_values("return_20d", ascending=False)
        for rank, (_, row) in enumerate(perf.iterrows(), 1):
            sector_data = {
                "sector_code": row.get("sector_code", ""),
                "sector_name": row.get("sector_name", ""),
                "rank": rank,
                "return_1d": safe_float(row.get("return_1d", 0)),
                "return_5d": safe_float(row.get("return_5d", 0)),
                "return_20d": safe_float(row.get("return_20d", 0)),
                "return_60d": safe_float(row.get("return_60d", 0)),
                "volatility": safe_float(row.get("volatility", 0)),
                "member_count": safe_int(row.get("member_count", 0)),
                "turnover_amount": safe_float(row.get("turnover_amount", 0)),
                "amount_5d_avg": safe_float(row.get("amount_5d_avg", 0)),
                "amount_share": safe_float(row.get("amount_share", 0)),
                "amount_source": str(row.get("amount_source", "missing")),
                "data_source": str(row.get("data_source", "missing")),
            }
            sector_data["signals"] = _signal_map(sigs, sector_data["sector_name"])
            sectors.append(sector_data)

    top_performers = [s for s in sectors[:5] if s.get("return_5d", 0) > 0]
    bottom_performers = [s for s in sectors[-5:] if s.get("return_5d", 0) < 0]

    signal_dispersion = 0.0
    if sectors and any(s.get("signals") for s in sectors):
        all_ratios = [
            data.get("buy_ratio", 0)
            for sector in sectors
            for data in (sector.get("signals") or {}).values()
            if isinstance(data, dict)
        ]
        if all_ratios:
            import numpy as np
            signal_dispersion = round(float(np.std(all_ratios)), 4)

    return {
        "sectors": sectors,
        "total_sectors": len(sectors),
        "top_performers": top_performers,
        "bottom_performers": bottom_performers,
        "signal_dispersion": signal_dispersion,
        "data_source": source_summary(sectors),
        "capital_source": capital_source_summary(sectors),
        "freshness": {
            "performance": perf_path.name if perf_path else "",
            "signals": sig_path.name if sig_path else "",
        },
    }


def build_sector_exposure() -> dict:
    exp_path, df = _read_snapshot("sector_exposure_snapshot")
    if exp_path is None or df.empty:
        return {"exposure": [], "total_sectors": 0, "data_source": "missing"}

    exposure = [
        {
            "sector": row.get("sector", ""),
            "date": str(row.get("date", "")),
            "weight": safe_float(row.get("weight", 0)),
            "market_value": safe_float(row.get("market_value", 0)),
            "position_count": safe_int(row.get("position_count", 0)),
        }
        for _, row in df.iterrows()
    ]
    exposure = sorted(exposure, key=lambda row: row["weight"], reverse=True)
    return {"exposure": exposure, "total_sectors": len(exposure), "data_source": "real"}


def build_sector_detail(industry: str) -> dict:
    _, perf = _read_snapshot("sector_performance_snapshot")
    _, sigs = _read_snapshot("sector_signal_snapshot")

    perf_row = {}
    if not perf.empty:
        match = perf[perf["sector_name"] == industry]
        if not match.empty:
            for key, value in match.iloc[0].to_dict().items():
                if key == "member_count":
                    perf_row[key] = safe_int(value)
                elif key.startswith("return_") or key in {"volatility"}:
                    perf_row[key] = safe_float(value)
                else:
                    perf_row[key] = "" if pd.isna(value) else value

    return {
        "sector_name": industry,
        "performance": perf_row,
        "signals": _signal_map(sigs, industry),
        "data_source": perf_row.get("data_source", "missing"),
    }
