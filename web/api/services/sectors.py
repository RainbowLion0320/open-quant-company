"""Sector API domain service."""

from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from data.datahub import get_datahub
from web.api.serializers import safe_float, safe_int
from web.api.services.snapshots import latest_hub_snapshot

HUB = get_datahub()
CONSTITUENT_LIMIT = 5


def latest_snapshot(dimension: str):
    return latest_hub_snapshot(HUB, dimension)


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
    path = latest_snapshot(dimension)
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


@lru_cache(maxsize=1)
def _symbol_name_map() -> dict[str, str]:
    path = HUB.project_root / "data" / "universe_raw.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, list):
        return {}
    return {
        str(item.get("code", "")): str(item.get("name", "") or item.get("code", ""))
        for item in raw
        if isinstance(item, dict) and item.get("code")
    }


@lru_cache(maxsize=1)
def _stock_metrics_snapshot() -> dict[str, dict]:
    """Latest per-stock amount and 5-day return for sector block children."""
    stock_glob = HUB.store_path("stock") / "daily" / "*.parquet"
    if not stock_glob.parent.exists():
        return {}

    try:
        import duckdb

        query = f"""
        WITH raw AS (
            SELECT
                regexp_extract(filename, '([^/]+)\\.parquet$', 1) AS symbol,
                TRY_CAST(date AS DATE) AS trade_date,
                TRY_CAST(close AS DOUBLE) AS close,
                TRY_CAST(COALESCE(amount, close * volume) AS DOUBLE) AS amount
            FROM read_parquet('{stock_glob}', filename=true, union_by_name=true)
            WHERE close IS NOT NULL
        ),
        ranked AS (
            SELECT
                *,
                row_number() OVER (
                    PARTITION BY symbol
                    ORDER BY trade_date DESC NULLS LAST
                ) AS rn
            FROM raw
        ),
        agg AS (
            SELECT
                symbol,
                max(CASE WHEN rn = 1 THEN amount END) AS turnover_amount,
                avg(CASE WHEN rn <= 5 THEN amount END) AS amount_5d_avg,
                max(CASE WHEN rn = 1 THEN close END) AS close_now,
                max(CASE WHEN rn = 6 THEN close END) AS close_5d_ago
            FROM ranked
            WHERE rn <= 6
            GROUP BY symbol
        )
        SELECT
            symbol,
            turnover_amount,
            amount_5d_avg,
            CASE
                WHEN close_5d_ago IS NOT NULL AND close_5d_ago != 0
                THEN close_now / close_5d_ago - 1
                ELSE 0
            END AS return_5d
        FROM agg
        """
        df = duckdb.connect(":memory:").execute(query).fetch_df()
    except Exception:
        return {}

    metrics: dict[str, dict] = {}
    for _, row in df.iterrows():
        symbol = str(row.get("symbol", ""))
        if not symbol:
            continue
        metrics[symbol] = {
            "amount": safe_float(row.get("amount_5d_avg", row.get("turnover_amount", 0))),
            "turnover_amount": safe_float(row.get("turnover_amount", 0)),
            "return_5d": safe_float(row.get("return_5d", 0)),
        }
    return metrics


def _normalize_constituent_weights(blocks: list[dict]) -> list[dict]:
    if not blocks:
        return []
    total = sum(max(safe_float(block.get("amount", 0)), 0.0) for block in blocks)
    if total <= 0:
        weight = round(1 / len(blocks), 4)
        for block in blocks:
            block["weight"] = weight
        blocks[-1]["weight"] = round(max(0.0, 1.0 - weight * (len(blocks) - 1)), 4)
        return blocks

    running = 0.0
    for block in blocks[:-1]:
        weight = round(max(safe_float(block.get("amount", 0)), 0.0) / total, 4)
        block["weight"] = weight
        running += weight
    blocks[-1]["weight"] = round(max(0.0, 1.0 - running), 4)
    return blocks


def _sector_constituents(sector_name: str, limit: int = CONSTITUENT_LIMIT) -> list[dict]:
    mem_path = HUB.dimension_path("sector_membership")
    if not mem_path.exists():
        return []

    mem = HUB.read_parquet(mem_path, default=pd.DataFrame())
    if mem.empty or "sector_name" not in mem.columns or "symbol" not in mem.columns:
        return []

    sector_symbols = [
        str(symbol)
        for symbol in mem[mem["sector_name"] == sector_name]["symbol"].tolist()
        if str(symbol)
    ]
    if not sector_symbols:
        return []

    names = _symbol_name_map()
    metrics = _stock_metrics_snapshot()
    rows: list[dict] = []
    for symbol in sector_symbols:
        metric = metrics.get(symbol)
        if not metric:
            continue
        amount = max(safe_float(metric.get("amount", 0)), 0.0)
        if amount <= 0:
            continue
        rows.append({
            "symbol": symbol,
            "name": names.get(symbol, symbol),
            "amount": round(amount, 2),
            "return_5d": round(safe_float(metric.get("return_5d", 0)), 6),
            "kind": "stock",
        })

    if not rows:
        rows = [
            {
                "symbol": symbol,
                "name": names.get(symbol, symbol),
                "amount": 1.0,
                "return_5d": 0.0,
                "kind": "stock",
            }
            for symbol in sector_symbols[:limit]
        ]
        if len(sector_symbols) > limit:
            rows.append({
                "symbol": "__others__",
                "name": "其他",
                "amount": float(len(sector_symbols) - limit),
                "return_5d": 0.0,
                "kind": "others",
            })
        return _normalize_constituent_weights(rows)

    rows = sorted(rows, key=lambda item: item["amount"], reverse=True)
    top = rows[:limit]
    rest = rows[limit:]
    if rest:
        rest_amount = sum(max(safe_float(item.get("amount", 0)), 0.0) for item in rest)
        rest_return = (
            sum(safe_float(item.get("return_5d", 0)) * max(safe_float(item.get("amount", 0)), 0.0) for item in rest)
            / rest_amount
            if rest_amount > 0
            else 0.0
        )
        top.append({
            "symbol": "__others__",
            "name": "其他",
            "amount": round(rest_amount, 2),
            "return_5d": round(rest_return, 6),
            "kind": "others",
        })

    return _normalize_constituent_weights(top)


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
            sector_data["constituents"] = _sector_constituents(sector_data["sector_name"])
            sectors.append(sector_data)

    top_performers = [s for s in sectors[:5] if s.get("return_5d", 0) > 0]
    bottom_performers = [s for s in sectors[-5:] if s.get("return_5d", 0) < 0]

    signal_concentration = 0.0
    if sectors and any(s.get("signals") for s in sectors):
        all_ratios = [
            data.get("buy_ratio", 0)
            for sector in sectors
            for data in (sector.get("signals") or {}).values()
            if isinstance(data, dict)
        ]
        if all_ratios:
            import numpy as np
            signal_concentration = round(float(np.std(all_ratios)), 4)

    return {
        "sectors": sectors,
        "total_sectors": len(sectors),
        "top_performers": top_performers,
        "bottom_performers": bottom_performers,
        "signal_concentration": signal_concentration,
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
    return {"exposure": exposure, "total_sectors": len(exposure), "data_source": "real"}


def build_sector_stocks(industry: str) -> dict:
    mem_path = HUB.dimension_path("sector_membership")
    if not mem_path.exists():
        return {"industry": industry, "stocks": [], "data_source": "missing"}

    mem = HUB.read_parquet(mem_path, default=pd.DataFrame())
    if mem.empty:
        return {"industry": industry, "stocks": [], "data_source": "missing"}

    sector_symbols = mem[mem["sector_name"] == industry]["symbol"].tolist()
    stocks = [{"symbol": symbol} for symbol in sector_symbols[:50]]
    return {
        "industry": industry,
        "stocks": stocks,
        "total": len(sector_symbols),
        "data_source": "real",
    }


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
