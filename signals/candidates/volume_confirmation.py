"""Candidate volume-confirmation strategy."""
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
    volume_ratio,
)


def compute(limit: int = 0) -> list[dict]:
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=25)
        if df.empty:
            continue
        close = close_series(df)
        turnover = pd.to_numeric(df.get("turnover", pd.Series(dtype="float64")), errors="coerce").dropna()
        amount = pd.to_numeric(df.get("amount", pd.Series(dtype="float64")), errors="coerce").dropna()
        flow_proxy = float(turnover.tail(20).mean()) if len(turnover) else float(amount.tail(20).mean() if len(amount) else 0.0)
        metrics.append(
            {
                "symbol": symbol,
                "volume_ratio_20d": volume_ratio(df, 20),
                "price_momentum_20d": pct_return(close, 20),
                "turnover_moneyflow_proxy": flow_proxy,
            }
        )

    volume_rank = percentile_score(pd.Series({m["symbol"]: m["volume_ratio_20d"] for m in metrics}))
    momentum_rank = percentile_score(pd.Series({m["symbol"]: m["price_momentum_20d"] for m in metrics}))
    flow_rank = percentile_score(pd.Series({m["symbol"]: m["turnover_moneyflow_proxy"] for m in metrics}))
    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = (
            volume_rank.get(symbol, 0.0) * 0.45
            + momentum_rank.get(symbol, 0.0) * 0.35
            + flow_rank.get(symbol, 0.0) * 0.20
        )
        rows.append(
            build_signal_row(
                symbol=symbol,
                name=stock_name(symbol),
                industry=stock_industry(symbol),
                score=score,
                signal="hold",
                detail={
                    "strategy": "volume_confirmation",
                    "volume_ratio_20d": round(item["volume_ratio_20d"], 3),
                    "volume_rank": volume_rank.get(symbol, 0.0),
                    "price_momentum_20d": round(item["price_momentum_20d"], 4),
                    "momentum_rank": momentum_rank.get(symbol, 0.0),
                    "turnover_moneyflow_proxy": round(item["turnover_moneyflow_proxy"], 4),
                    "flow_rank": flow_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "volume_confirmation", min_score=55.0, max_buys=20)
