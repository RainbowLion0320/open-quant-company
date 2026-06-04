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
from signals.candidates.params import candidate_strategy_params


def compute(limit: int = 0) -> list[dict]:
    params = candidate_strategy_params("low_vol_defensive")
    weights = params["score_weights"]
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=int(params["min_history_days"]))
        if df.empty:
            continue
        close = close_series(df)
        amount = pd.to_numeric(df.get("amount", pd.Series(dtype="float64")), errors="coerce").dropna()
        metrics.append(
            {
                "symbol": symbol,
                "volatility": annualized_volatility(close, int(params["volatility_window"])),
                "drawdown_control": drawdown_control_score(close, int(params["drawdown_window"])),
                "trend": bounded_score(
                    float(params["trend_score_base"])
                    + pct_return(close, int(params["trend_window"])) * float(params["trend_score_scale"])
                ),
                "liquidity": float(amount.tail(int(params["liquidity_window"])).mean()) if len(amount) else 0.0,
            }
        )

    inverse_vol_rank = percentile_score(pd.Series({m["symbol"]: -m["volatility"] for m in metrics}))
    liquidity_rank = percentile_score(pd.Series({m["symbol"]: m["liquidity"] for m in metrics}))
    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = (
            inverse_vol_rank.get(symbol, 0.0) * float(weights["inverse_volatility"])
            + item["drawdown_control"] * float(weights["drawdown_control"])
            + item["trend"] * float(weights["trend"])
            + liquidity_rank.get(symbol, 0.0) * float(weights["liquidity"])
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
                    "volatility": round(item["volatility"], 4),
                    "inverse_vol_rank": inverse_vol_rank.get(symbol, 0.0),
                    "drawdown_control": item["drawdown_control"],
                    "trend_score": item["trend"],
                    "liquidity_rank": liquidity_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "low_vol_defensive")
