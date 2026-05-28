"""Candidate sector rotation strategy."""
from __future__ import annotations

import pandas as pd

from signals.candidates.common import (
    build_signal_row,
    candidate_symbols,
    close_series,
    pct_return,
    percentile_score,
    price_frame,
    selected_candidate_rows,
    stock_industry,
    stock_name,
)


def compute(limit: int = 0) -> list[dict]:
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=70)
        if df.empty:
            continue
        close = close_series(df)
        metrics.append(
            {
                "symbol": symbol,
                "industry": stock_industry(symbol),
                "return_20d": pct_return(close, 20),
                "return_60d": pct_return(close, 60),
            }
        )

    if not metrics:
        return []

    metric_df = pd.DataFrame(metrics)
    industry_20d = metric_df.groupby("industry")["return_20d"].median()
    industry_60d = metric_df.groupby("industry")["return_60d"].median()
    industry_20d_rank = percentile_score(industry_20d)
    industry_60d_rank = percentile_score(industry_60d)

    stock_rank: dict[str, float] = {}
    for _, group in metric_df.groupby("industry"):
        stock_rank.update(percentile_score(group.set_index("symbol")["return_20d"]))

    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        industry = item["industry"]
        score = (
            industry_20d_rank.get(industry, 0.0) * 0.60
            + industry_60d_rank.get(industry, 0.0) * 0.25
            + stock_rank.get(symbol, 0.0) * 0.15
        )
        rows.append(
            build_signal_row(
                symbol=symbol,
                name=stock_name(symbol),
                industry=industry,
                score=score,
                signal="hold",
                detail={
                    "strategy": "sector_rotation",
                    "industry_return_20d": round(float(industry_20d.get(industry, 0.0)), 4),
                    "industry_return_60d": round(float(industry_60d.get(industry, 0.0)), 4),
                    "industry_20d_rank": industry_20d_rank.get(industry, 0.0),
                    "industry_60d_rank": industry_60d_rank.get(industry, 0.0),
                    "stock_score_inside_industry": stock_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "sector_rotation", min_score=55.0, max_buys=20)
