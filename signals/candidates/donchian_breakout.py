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


def compute(limit: int = 0) -> list[dict]:
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=60)
        if df.empty:
            continue
        close = close_series(df)
        high = pd.to_numeric(df.get("high", close), errors="coerce").dropna()
        if close.empty or high.empty:
            continue
        latest = safe_float(close.iloc[-1])
        high_55 = safe_float(high.tail(55).max())
        metrics.append(
            {
                "symbol": symbol,
                "proximity": bounded_score(latest / high_55 * 100.0 if high_55 else 0.0),
                "volume_ratio": volume_ratio(df, 20),
                "volatility": annualized_volatility(close, 20),
            }
        )

    volume_rank = percentile_score(pd.Series({m["symbol"]: m["volume_ratio"] for m in metrics}))
    inverse_vol_rank = percentile_score(pd.Series({m["symbol"]: -m["volatility"] for m in metrics}))
    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = (
            item["proximity"] * 0.60
            + volume_rank.get(symbol, 0.0) * 0.20
            + inverse_vol_rank.get(symbol, 0.0) * 0.20
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
                    "high_55_proximity": item["proximity"],
                    "volume_ratio_20d": round(item["volume_ratio"], 3),
                    "volume_rank": volume_rank.get(symbol, 0.0),
                    "volatility_20d": round(item["volatility"], 4),
                    "inverse_vol_rank": inverse_vol_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "donchian_breakout", min_score=60.0, max_buys=20)
