"""Candidate trend-following strategy."""
from __future__ import annotations

import pandas as pd

from signals.candidates.common import (
    build_signal_row,
    candidate_symbols,
    close_series,
    moving_average,
    pct_return,
    percentile_score,
    price_frame,
    safe_float,
    selected_candidate_rows,
    stock_industry,
    stock_name,
)
from signals.candidates.params import candidate_strategy_params


def compute(limit: int = 0) -> list[dict]:
    params = candidate_strategy_params("trend_following")
    weights = params["score_weights"]
    score_values = params["trend_score_values"]
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=int(params["min_history_days"]))
        if df.empty:
            continue
        close = close_series(df)
        short_ma = moving_average(close, int(params["short_ma_window"]))
        medium_ma = moving_average(close, int(params["medium_ma_window"]))
        long_ma = moving_average(close, int(params["long_ma_window"]))
        latest = safe_float(close.iloc[-1])
        trend_score = 0.0
        if latest > short_ma > medium_ma:
            trend_score = float(score_values["strong"])
        elif short_ma > medium_ma:
            trend_score = float(score_values["medium"])
        elif latest > medium_ma:
            trend_score = float(score_values["price_above_medium"])
        elif latest > long_ma:
            trend_score = float(score_values["price_above_long"])
        metrics.append(
            {
                "symbol": symbol,
                "trend": trend_score,
                "long_ma": 100.0 if long_ma and latest > long_ma else 0.0,
                "momentum": pct_return(close, int(params["momentum_window"])),
            }
        )

    momentum_rank = percentile_score(pd.Series({m["symbol"]: m["momentum"] for m in metrics}))
    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = (
            item["trend"] * float(weights["trend"])
            + item["long_ma"] * float(weights["above_long_ma"])
            + momentum_rank.get(symbol, 0.0) * float(weights["momentum"])
        )
        rows.append(
            build_signal_row(
                symbol=symbol,
                name=stock_name(symbol),
                industry=stock_industry(symbol),
                score=score,
                signal="hold",
                detail={
                    "strategy": "trend_following",
                    "trend_score": round(item["trend"], 2),
                    "above_long_ma_score": round(item["long_ma"], 2),
                    "momentum_return": round(item["momentum"], 4),
                    "momentum_rank": momentum_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "trend_following")
