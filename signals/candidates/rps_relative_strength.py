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


def compute(limit: int = 0) -> list[dict]:
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=130)
        if df.empty:
            continue
        close = close_series(df)
        latest = safe_float(close.iloc[-1])
        ma120 = moving_average(close, 120)
        metrics.append(
            {
                "symbol": symbol,
                "rps_3m_skip_1m": pct_return(close, 42, skip_recent=21),
                "rps_6m_skip_1m": pct_return(close, 105, skip_recent=21),
                "trend_filter": 100.0 if ma120 and latest > ma120 else 0.0,
            }
        )

    rps_3m_rank = percentile_score(pd.Series({m["symbol"]: m["rps_3m_skip_1m"] for m in metrics}))
    rps_6m_rank = percentile_score(pd.Series({m["symbol"]: m["rps_6m_skip_1m"] for m in metrics}))
    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = (
            rps_3m_rank.get(symbol, 0.0) * 0.45
            + rps_6m_rank.get(symbol, 0.0) * 0.45
            + item["trend_filter"] * 0.10
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
                    "rps_3m_skip_1m": round(item["rps_3m_skip_1m"], 4),
                    "rps_3m_rank": rps_3m_rank.get(symbol, 0.0),
                    "rps_6m_skip_1m": round(item["rps_6m_skip_1m"], 4),
                    "rps_6m_rank": rps_6m_rank.get(symbol, 0.0),
                    "trend_filter": item["trend_filter"],
                },
            )
        )
    return selected_candidate_rows(rows, "rps_relative_strength", min_score=55.0, max_buys=20)
