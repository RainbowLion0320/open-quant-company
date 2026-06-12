"""Strategy-level data readiness helpers for formal backtest artifacts."""

from __future__ import annotations

import pandas as pd

_HEALTH_ROWS_CACHE = None

REQUIREMENT_DIMENSIONS = {
    "financials": ["financial_summary", "fina_indicator", "income_statement", "balance_sheet", "cashflow_statement"],
    "valuation_daily": ["valuation_daily"],
    "stock_daily": ["ohlcv_daily", "adj_factor"],
    "sector": ["sector_sw_daily", "sector_membership"],
    "moneyflow": ["moneyflow_daily", "moneyflow_tushare_daily"],
    "market_regime": ["ohlcv_daily", "bond_treasury_yields"],
    "portfolio": [],
    "features": [],
}


def _health_rows():
    global _HEALTH_ROWS_CACHE
    if _HEALTH_ROWS_CACHE is not None:
        return _HEALTH_ROWS_CACHE
    try:
        from astrolabe_cli.commands.data import run_health_check_quiet

        _HEALTH_ROWS_CACHE = run_health_check_quiet()
    except Exception:
        _HEALTH_ROWS_CACHE = pd.DataFrame()
    return _HEALTH_ROWS_CACHE


def strategy_data_readiness(item: dict) -> dict:
    requirements = [str(req) for req in item.get("data_requirements", [])]
    required_dimensions = sorted(
        {dim for req in requirements for dim in REQUIREMENT_DIMENSIONS.get(req, [])}
    )
    if not required_dimensions:
        return _payload("ok", requirements, required_dimensions, [], [], [], {})

    rows = _health_rows()
    if rows is None or not hasattr(rows, "iterrows") or rows.empty:
        return _payload("blocked", requirements, required_dimensions, ["data_health_unavailable"], [], required_dimensions, {})

    registry_rows = {
        str(row.get("registry_key") or row.get("table") or ""): row
        for _, row in rows.iterrows()
    }
    blockers: list[str] = []
    stale: list[str] = []
    missing: list[str] = []
    statuses: dict[str, str] = {}
    for dimension in required_dimensions:
        row = registry_rows.get(dimension)
        if row is None:
            missing.append(dimension)
            blockers.append(f"missing_data:{dimension}")
            statuses[dimension] = "missing"
            continue
        status = str(row.get("freshness_status") or row.get("status") or "unknown").lower()
        statuses[dimension] = status
        if status in {"missing", "error"}:
            missing.append(dimension)
            blockers.append(f"missing_data:{dimension}")
        elif status == "stale":
            stale.append(dimension)
            blockers.append(f"stale_data:{dimension}")
    return _payload("ok" if not blockers else "blocked", requirements, required_dimensions, blockers, stale, missing, statuses)


def _payload(
    status: str,
    requirements: list[str],
    required_dimensions: list[str],
    blockers: list[str],
    stale: list[str],
    missing: list[str],
    statuses: dict[str, str],
) -> dict:
    return {
        "status": status,
        "requirements": requirements,
        "required_dimensions": required_dimensions,
        "blockers": blockers,
        "stale": stale,
        "missing": missing,
        "statuses": statuses,
    }
