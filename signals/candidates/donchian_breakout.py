"""Candidate Donchian breakout strategy."""
from __future__ import annotations

import pandas as pd

from signals.candidates.common import (
    annualized_volatility,
    bounded_score,
    build_signal_row,
    candidate_symbols,
    close_series,
    percentile_score,
    price_frame,
    safe_float,
    selected_candidate_rows,
    stock_industry,
    stock_name,
    volume_ratio,
)
from signals.candidates.params import candidate_strategy_params


def compute(limit: int = 0) -> list[dict]:
    params = candidate_strategy_params("donchian_breakout")
    weights = params["score_weights"]
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=int(params["min_history_days"]))
        if df.empty:
            continue
        close = close_series(df)
        high = pd.to_numeric(df.get("high", close), errors="coerce").dropna()
        if close.empty or high.empty:
            continue
        latest = safe_float(close.iloc[-1])
        high_window = safe_float(high.tail(int(params["breakout_window"])).max())
        metrics.append(
            {
                "symbol": symbol,
                "proximity": bounded_score(latest / high_window * 100.0 if high_window else 0.0),
                "volume_ratio": volume_ratio(df, int(params["volume_window"])),
                "volatility": annualized_volatility(close, int(params["volatility_window"])),
            }
        )

    volume_rank = percentile_score(pd.Series({m["symbol"]: m["volume_ratio"] for m in metrics}))
    inverse_vol_rank = percentile_score(pd.Series({m["symbol"]: -m["volatility"] for m in metrics}))
    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = (
            item["proximity"] * float(weights["breakout_proximity"])
            + volume_rank.get(symbol, 0.0) * float(weights["volume"])
            + inverse_vol_rank.get(symbol, 0.0) * float(weights["inverse_volatility"])
        )
        rows.append(
            build_signal_row(
                symbol=symbol,
                name=stock_name(symbol),
                industry=stock_industry(symbol),
                score=score,
                signal="hold",
                detail={
                    "strategy": "donchian_breakout",
                    "breakout_proximity": item["proximity"],
                    "volume_ratio": round(item["volume_ratio"], 3),
                    "volume_rank": volume_rank.get(symbol, 0.0),
                    "volatility": round(item["volatility"], 4),
                    "inverse_vol_rank": inverse_vol_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "donchian_breakout")
