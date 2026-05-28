"""Candidate low-volatility defensive strategy."""
from __future__ import annotations

import pandas as pd

from signals.candidates.common import (
    annualized_volatility,
    bounded_score,
    build_signal_row,
    candidate_symbols,
    close_series,
    drawdown_control_score,
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
        amount = pd.to_numeric(df.get("amount", pd.Series(dtype="float64")), errors="coerce").dropna()
        metrics.append(
            {
                "symbol": symbol,
                "volatility_60d": annualized_volatility(close, 60),
                "drawdown_control": drawdown_control_score(close, 60),
                "trend_20d": bounded_score(50.0 + pct_return(close, 20) * 500.0),
                "liquidity": float(amount.tail(20).mean()) if len(amount) else 0.0,
            }
        )

    inverse_vol_rank = percentile_score(pd.Series({m["symbol"]: -m["volatility_60d"] for m in metrics}))
    liquidity_rank = percentile_score(pd.Series({m["symbol"]: m["liquidity"] for m in metrics}))
    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = (
            inverse_vol_rank.get(symbol, 0.0) * 0.40
            + item["drawdown_control"] * 0.30
            + item["trend_20d"] * 0.20
            + liquidity_rank.get(symbol, 0.0) * 0.10
        )
        rows.append(
            build_signal_row(
                symbol=symbol,
                name=stock_name(symbol),
                industry=stock_industry(symbol),
                score=score,
                signal="hold",
                detail={
                    "strategy": "low_vol_defensive",
                    "volatility_60d": round(item["volatility_60d"], 4),
                    "inverse_vol_rank": inverse_vol_rank.get(symbol, 0.0),
                    "drawdown_control": item["drawdown_control"],
                    "trend_20d_score": item["trend_20d"],
                    "liquidity_rank": liquidity_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "low_vol_defensive", min_score=55.0, max_buys=20)
