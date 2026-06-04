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
from signals.candidates.params import candidate_strategy_params


def compute(limit: int = 0) -> list[dict]:
    params = candidate_strategy_params("sector_rotation")
    weights = params["score_weights"]
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=int(params["min_history_days"]))
        if df.empty:
            continue
        close = close_series(df)
        metrics.append(
            {
                "symbol": symbol,
                "industry": stock_industry(symbol),
                "short_return": pct_return(close, int(params["short_return_window"])),
                "long_return": pct_return(close, int(params["long_return_window"])),
            }
        )

    if not metrics:
        return []

    metric_df = pd.DataFrame(metrics)
    industry_short = metric_df.groupby("industry")["short_return"].median()
    industry_long = metric_df.groupby("industry")["long_return"].median()
    industry_short_rank = percentile_score(industry_short)
    industry_long_rank = percentile_score(industry_long)

    stock_rank: dict[str, float] = {}
    for _, group in metric_df.groupby("industry"):
        stock_rank.update(percentile_score(group.set_index("symbol")["short_return"]))

    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        industry = item["industry"]
        score = (
            industry_short_rank.get(industry, 0.0) * float(weights["industry_short"])
            + industry_long_rank.get(industry, 0.0) * float(weights["industry_long"])
            + stock_rank.get(symbol, 0.0) * float(weights["stock_inside_industry"])
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
                    "industry_short_return": round(float(industry_short.get(industry, 0.0)), 4),
                    "industry_long_return": round(float(industry_long.get(industry, 0.0)), 4),
                    "industry_short_rank": industry_short_rank.get(industry, 0.0),
                    "industry_long_rank": industry_long_rank.get(industry, 0.0),
                    "stock_score_inside_industry": stock_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "sector_rotation")
