"""Sector / Industry API — radar overview, detail, stocks, exposure."""

from fastapi import APIRouter, Query
import pandas as pd
from pathlib import Path
from typing import Any

from data.datahub import get_datahub

router = APIRouter(prefix="/api/sectors", tags=["Sectors"])

HUB = get_datahub()


def _sector_store() -> Path:
    return HUB.store_root / "sector"


def _latest_snapshot(dimension: str, legacy_prefix: str) -> Path | None:
    """Find the latest registry-backed snapshot, with legacy flat-file fallback."""
    try:
        root = HUB.dimension_root(dimension)
        if root.exists():
            registry_candidates = sorted(root.glob("*.parquet"), reverse=True)
            if registry_candidates:
                return registry_candidates[0]
    except Exception:
        pass

    store = _sector_store()
    if not store.exists():
        return None
    legacy_candidates = sorted(store.glob(f"{legacy_prefix}*.parquet"), reverse=True)
    return legacy_candidates[0] if legacy_candidates else None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        if pd.isna(n):
            return default
        return n
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(value)
    except Exception:
        return default


def _source_summary(sectors: list[dict]) -> str:
    sources = {str(s.get("data_source", "missing")) for s in sectors}
    if "real" in sources:
        return "real"
    if "proxy" in sources:
        return "proxy"
    return "missing"


# ═══════════════════════════════════════
# GET /api/sectors/overview
# ═══════════════════════════════════════

@router.get("/overview")
def sector_overview():
    """Return sector performance ranking + signal summary."""
    perf_path = _latest_snapshot("sector_performance_snapshot", "sector_performance_")
    sig_path = _latest_snapshot("sector_signal_snapshot", "sector_signals_")

    perf = pd.DataFrame()
    sigs = pd.DataFrame()

    if perf_path:
        perf = HUB.read_parquet(perf_path, default=pd.DataFrame())

    if sig_path:
        sigs = HUB.read_parquet(sig_path, default=pd.DataFrame())

    # Rankings
    sectors = []
    if not perf.empty:
        perf = perf.sort_values("return_20d", ascending=False)
        for rank, (_, row) in enumerate(perf.iterrows(), 1):
            sector_data = {
                "sector_code": row.get("sector_code", ""),
                "sector_name": row.get("sector_name", ""),
                "rank": rank,
                "return_1d": _safe_float(row.get("return_1d", 0)),
                "return_5d": _safe_float(row.get("return_5d", 0)),
                "return_20d": _safe_float(row.get("return_20d", 0)),
                "return_60d": _safe_float(row.get("return_60d", 0)),
                "volatility": _safe_float(row.get("volatility", 0)),
                "member_count": _safe_int(row.get("member_count", 0)),
                "data_source": str(row.get("data_source", "missing")),
            }
            # Strategy signals for this sector
            sector_sigs = {}
            if not sigs.empty:
                sec_sigs = sigs[sigs["sector"] == sector_data["sector_name"]]
                for _, sr in sec_sigs.iterrows():
                    strategy = str(sr.get("strategy", ""))
                    sector_sigs[strategy] = {
                        "total": _safe_int(sr.get("total", 0)),
                        "buy_count": _safe_int(sr.get("buy_count", 0)),
                        "buy_ratio": _safe_float(sr.get("buy_ratio", 0)),
                        "avg_score": _safe_float(sr.get("avg_score", 0)),
                        "top_symbol": str(sr.get("top_symbol", "")),
                    }
            sector_data["signals"] = sector_sigs
            sectors.append(sector_data)

    # Summary stats
    top_performers = [s for s in sectors[:5] if s.get("return_5d", 0) > 0]
    bottom_performers = [s for s in sectors[-5:] if s.get("return_5d", 0) < 0]

    signal_concentration = 0.0
    if sectors and any(s.get("signals") for s in sectors):
        all_ratios = []
        for s in sectors:
            for st_data in (s.get("signals") or {}).values():
                if isinstance(st_data, dict):
                    all_ratios.append(st_data.get("buy_ratio", 0))
        if all_ratios:
            import numpy as np
            signal_concentration = round(float(np.std(all_ratios)), 4)

    return {
        "sectors": sectors,
        "total_sectors": len(sectors),
        "top_performers": top_performers,
        "bottom_performers": bottom_performers,
        "signal_concentration": signal_concentration,
        "data_source": _source_summary(sectors),
        "freshness": {
            "performance": perf_path.name if perf_path else "",
            "signals": sig_path.name if sig_path else "",
        },
    }


# ═══════════════════════════════════════
# GET /api/sectors/exposure  (MUST be before /{industry} to avoid capture)
# ═══════════════════════════════════════

@router.get("/exposure")
def sector_exposure():
    """Return portfolio exposure by sector."""
    exp_path = _latest_snapshot("sector_exposure_snapshot", "sector_exposure_")
    if not exp_path:
        return {"exposure": [], "total_sectors": 0, "data_source": "missing"}

    df = HUB.read_parquet(exp_path, default=pd.DataFrame())
    if df.empty:
        return {"exposure": [], "total_sectors": 0, "data_source": "missing"}

    exposure = []
    for _, row in df.iterrows():
        exposure.append({
            "sector": row.get("sector", ""),
            "date": str(row.get("date", "")),
            "weight": _safe_float(row.get("weight", 0)),
            "market_value": _safe_float(row.get("market_value", 0)),
            "position_count": _safe_int(row.get("position_count", 0)),
        })

    return {
        "exposure": exposure,
        "total_sectors": len(exposure),
        "data_source": "real",
    }


# ═══════════════════════════════════════
# GET /api/sectors/{industry}/stocks  (MUST be before /{industry} to avoid capture)
# ═══════════════════════════════════════

@router.get("/{industry:path}/stocks")
def sector_stocks(industry: str):
    """Return member stocks for a sector with signal status."""
    from urllib.parse import unquote
    industry = unquote(industry)

    mem_path = HUB.dimension_path("sector_membership")
    if not mem_path.exists():
        return {"industry": industry, "stocks": [], "data_source": "missing"}

    mem = HUB.read_parquet(mem_path, default=pd.DataFrame())
    if mem.empty:
        return {"industry": industry, "stocks": [], "data_source": "missing"}

    sector_symbols = mem[mem["sector_name"] == industry]["symbol"].tolist()

    stocks = []
    for symbol in sector_symbols[:50]:  # cap response size
        stocks.append({"symbol": symbol})

    return {
        "industry": industry,
        "stocks": stocks,
        "total": len(sector_symbols),
        "data_source": "real",
    }


# ═══════════════════════════════════════
# GET /api/sectors/{industry}
# ═══════════════════════════════════════

@router.get("/{industry:path}")
def sector_detail(industry: str):
    """Return detail for a single sector: performance + signals + member count."""
    from urllib.parse import unquote
    industry = unquote(industry)

    perf_path = _latest_snapshot("sector_performance_snapshot", "sector_performance_")
    sig_path = _latest_snapshot("sector_signal_snapshot", "sector_signals_")

    perf = pd.DataFrame()
    sigs = pd.DataFrame()

    if perf_path:
        perf = HUB.read_parquet(perf_path, default=pd.DataFrame())

    if sig_path:
        sigs = HUB.read_parquet(sig_path, default=pd.DataFrame())

    perf_row = {}
    if not perf.empty:
        match = perf[perf["sector_name"] == industry]
        if not match.empty:
            r = match.iloc[0].to_dict()
            perf_row = {}
            for k, v in r.items():
                if k == "member_count":
                    perf_row[k] = _safe_int(v)
                elif k.startswith("return_") or k in {"volatility"}:
                    perf_row[k] = _safe_float(v)
                else:
                    perf_row[k] = "" if pd.isna(v) else v

    signals = {}
    if not sigs.empty:
        match = sigs[sigs["sector"] == industry]
        for _, sr in match.iterrows():
            strategy = str(sr.get("strategy", ""))
            signals[strategy] = {
                "total": _safe_int(sr.get("total", 0)),
                "buy_count": _safe_int(sr.get("buy_count", 0)),
                "buy_ratio": _safe_float(sr.get("buy_ratio", 0)),
                "avg_score": _safe_float(sr.get("avg_score", 0)),
                "top_symbol": str(sr.get("top_symbol", "")),
            }

    return {
        "sector_name": industry,
        "performance": perf_row,
        "signals": signals,
        "data_source": perf_row.get("data_source", "missing"),
    }
