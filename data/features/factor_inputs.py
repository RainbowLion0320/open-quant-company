"""Shared PIT fundamental and valuation factor helpers."""

from __future__ import annotations

from typing import Any

import pandas as pd


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace("%", "").replace(",", "").replace("万亿", "e12").replace("亿", "e8").replace("万", "e4")
        try:
            return float(normalized)
        except ValueError:
            return default
    return default


def compute_fundamental_factors(fin_df: pd.DataFrame, as_of: pd.Timestamp, *, default: float = 0.0) -> dict[str, float]:
    result: dict[str, float] = {}
    try:
        fin = fin_df.copy()
        report_col = "报告期" if "报告期" in fin.columns else "end_date"
        if report_col not in fin.columns:
            return result
        fin[report_col] = pd.to_datetime(fin[report_col], errors="coerce")
        past = fin[fin[report_col] <= as_of].sort_values(report_col)
        if len(past) == 0:
            return result
        latest = past.iloc[-1]
        result["fund_roe"] = to_float(latest.get("净资产收益率") or latest.get("roe"), default)
        result["fund_gross_margin"] = to_float(latest.get("销售毛利率") or latest.get("gross_margin"), default)
        result["fund_net_margin"] = to_float(latest.get("销售净利率") or latest.get("net_margin"), default)
        debt_equity = latest.get("debt_equity_ratio")
        if debt_equity is None and len(past) >= 2:
            previous = past.iloc[-2]
            debt_equity = float(previous.get("total_liab", 0) or 0) / max(1, float(previous.get("total_equity", 0) or 1))
        result["fund_de_ratio"] = to_float(debt_equity, default)
        result["fund_net_profit"] = to_float(latest.get("净利润") or latest.get("net_profit"), default)
        roes = [
            to_float(row.get("净资产收益率") or row.get("roe"), default)
            for _, row in past.tail(5).iterrows()
            if row.get("净资产收益率") or row.get("roe")
        ]
        result["fund_roe_5y_avg"] = sum(roes) / len(roes) if roes else default
        if len(past) >= 5:
            result["fund_gm_trend"] = result["fund_gross_margin"] - to_float(
                past.iloc[-5].get("销售毛利率") or past.iloc[-5].get("gross_margin") or 0,
                default,
            )
    except Exception:
        pass
    return result


def compute_valuation_factors(
    daily_df: pd.DataFrame,
    as_of: pd.Timestamp,
    *,
    default: float = 0.0,
    include_circ_mv: bool = False,
) -> dict[str, float]:
    result: dict[str, float] = {}
    try:
        past = daily_df[daily_df.index <= as_of]
        if len(past) == 0:
            return result
        latest = past.iloc[-1]
        for key, column in [
            ("val_pe", "pe"),
            ("val_pe_ttm", "pe_ttm"),
            ("val_pb", "pb"),
            ("val_ps", "ps"),
            ("val_dv_ratio", "dv_ratio"),
        ]:
            result[key] = to_float(latest.get(column), default)
        if len(past) > 250 and "pe_ttm" in past.columns:
            pe_hist = past["pe_ttm"].dropna().tail(500)
            if len(pe_hist) > 100:
                current = to_float(latest.get("pe_ttm"), default)
                if pd.notna(current) and current > 0:
                    result["val_pe_percentile"] = float((pe_hist < current).mean())
        result["val_total_mv"] = to_float(latest.get("total_mv"), default)
        if include_circ_mv:
            result["val_circ_mv"] = to_float(latest.get("circ_mv"), default)
    except Exception:
        pass
    return result
