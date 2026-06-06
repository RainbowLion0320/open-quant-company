"""Candidate quality-value strategy."""
from __future__ import annotations

import pandas as pd

from data.ingestion.fetchers.financial import read_financial_summary, read_valuation
from data.market.financials import extract_gross_margin_history, extract_roe_history
from signals.candidates.common import (
    build_signal_row,
    candidate_symbols,
    percentile_score,
    safe_float,
    selected_candidate_rows,
    stock_industry,
    stock_name,
)
from signals.candidates.params import candidate_strategy_params


def _latest_positive(df: pd.DataFrame | None, column: str) -> float:
    if df is None or df.empty or column not in df.columns:
        return 0.0
    frame = df.copy()
    if "trade_date" in frame.columns:
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
        frame = frame.sort_values("trade_date")
    values = pd.to_numeric(frame[column], errors="coerce").dropna()
    values = values[values > 0]
    return safe_float(values.iloc[-1]) if len(values) else 0.0


def _avg_recent(values: list[float], period_count: int) -> float:
    recent = [safe_float(v) for v in values[-period_count:] if safe_float(v) > 0]
    return sum(recent) / len(recent) if recent else 0.0


def compute(limit: int = 0) -> list[dict]:
    params = candidate_strategy_params("quality_value")
    weights = params["score_weights"]
    recent_period_count = int(params["recent_period_count"])
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        fin = read_financial_summary(symbol)
        valuation = read_valuation(symbol)
        roe = _avg_recent(extract_roe_history(fin), recent_period_count) if fin is not None else 0.0
        gross_margin = _avg_recent(extract_gross_margin_history(fin), recent_period_count) if fin is not None else 0.0
        pe_ttm = _latest_positive(valuation, "pe_ttm")
        pb = _latest_positive(valuation, "pb")
        metrics.append(
            {
                "symbol": symbol,
                "roe": roe,
                "gross_margin": gross_margin,
                "pe_ttm": pe_ttm,
                "pb": pb,
            }
        )

    roe_rank = percentile_score(pd.Series({m["symbol"]: m["roe"] for m in metrics}))
    gm_rank = percentile_score(pd.Series({m["symbol"]: m["gross_margin"] for m in metrics}))
    pe_rank = percentile_score(pd.Series({m["symbol"]: -m["pe_ttm"] for m in metrics if m["pe_ttm"] > 0}))
    pb_rank = percentile_score(pd.Series({m["symbol"]: -m["pb"] for m in metrics if m["pb"] > 0}))

    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = (
            roe_rank.get(symbol, 0.0) * float(weights["roe"])
            + gm_rank.get(symbol, 0.0) * float(weights["gross_margin"])
            + pe_rank.get(symbol, 0.0) * float(weights["inverse_pe"])
            + pb_rank.get(symbol, 0.0) * float(weights["inverse_pb"])
        )
        rows.append(
            build_signal_row(
                symbol=symbol,
                name=stock_name(symbol),
                industry=stock_industry(symbol),
                score=score,
                signal="hold",
                detail={
                    "strategy": "quality_value",
                    "roe_recent_avg": round(item["roe"], 4),
                    "roe_rank": roe_rank.get(symbol, 0.0),
                    "gross_margin_recent_avg": round(item["gross_margin"], 4),
                    "gross_margin_rank": gm_rank.get(symbol, 0.0),
                    "pe_ttm": round(item["pe_ttm"], 3),
                    "inverse_pe_rank": pe_rank.get(symbol, 0.0),
                    "pb": round(item["pb"], 3),
                    "inverse_pb_rank": pb_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "quality_value")
