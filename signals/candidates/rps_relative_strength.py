"""Candidate RPS relative-strength strategy."""
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
    params = candidate_strategy_params("rps_relative_strength")
    weights = params["score_weights"]
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=int(params["min_history_days"]))
        if df.empty:
            continue
        close = close_series(df)
        latest = safe_float(close.iloc[-1])
        trend_ma = moving_average(close, int(params["trend_ma_window"]))
        metrics.append(
            {
                "symbol": symbol,
                "short_rps_return": pct_return(
                    close,
                    int(params["short_return_window"]),
                    skip_recent=int(params["skip_recent_window"]),
                ),
                "long_rps_return": pct_return(
                    close,
                    int(params["long_return_window"]),
                    skip_recent=int(params["skip_recent_window"]),
                ),
                "trend_filter": 100.0 if trend_ma and latest > trend_ma else 0.0,
            }
        )

    short_rps_rank = percentile_score(pd.Series({m["symbol"]: m["short_rps_return"] for m in metrics}))
    long_rps_rank = percentile_score(pd.Series({m["symbol"]: m["long_rps_return"] for m in metrics}))
    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = (
            short_rps_rank.get(symbol, 0.0) * float(weights["short_rps"])
            + long_rps_rank.get(symbol, 0.0) * float(weights["long_rps"])
            + item["trend_filter"] * float(weights["trend_filter"])
        )
        rows.append(
            build_signal_row(
                symbol=symbol,
                name=stock_name(symbol),
                industry=stock_industry(symbol),
                score=score,
                signal="hold",
                detail={
                    "strategy": "rps_relative_strength",
                    "short_rps_return": round(item["short_rps_return"], 4),
                    "short_rps_rank": short_rps_rank.get(symbol, 0.0),
                    "long_rps_return": round(item["long_rps_return"], 4),
                    "long_rps_rank": long_rps_rank.get(symbol, 0.0),
                    "trend_filter": item["trend_filter"],
                },
            )
        )
    return selected_candidate_rows(rows, "rps_relative_strength")
