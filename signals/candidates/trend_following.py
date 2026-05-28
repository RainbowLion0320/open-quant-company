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


def compute(limit: int = 0) -> list[dict]:
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=130)
        if df.empty:
            continue
        close = close_series(df)
        ma20 = moving_average(close, 20)
        ma60 = moving_average(close, 60)
        ma120 = moving_average(close, 120)
        latest = safe_float(close.iloc[-1])
        trend_score = 0.0
        if latest > ma20 > ma60:
            trend_score = 100.0
        elif ma20 > ma60:
            trend_score = 75.0
        elif latest > ma60:
            trend_score = 50.0
        elif latest > ma120:
            trend_score = 25.0
        metrics.append(
            {
                "symbol": symbol,
                "trend": trend_score,
                "ma120": 100.0 if ma120 and latest > ma120 else 0.0,
                "momentum_60d": pct_return(close, 60),
            }
        )

    momentum_rank = percentile_score(pd.Series({m["symbol"]: m["momentum_60d"] for m in metrics}))
    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = item["trend"] * 0.40 + item["ma120"] * 0.30 + momentum_rank.get(symbol, 0.0) * 0.30
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
                    "above_ma120_score": round(item["ma120"], 2),
                    "momentum_60d": round(item["momentum_60d"], 4),
                    "momentum_rank": momentum_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "trend_following", min_score=55.0, max_buys=20)
