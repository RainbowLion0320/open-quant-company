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
from signals.candidates.params import candidate_strategy_params


def compute(limit: int = 0) -> list[dict]:
    params = candidate_strategy_params("volume_confirmation")
    weights = params["score_weights"]
    metrics: list[dict] = []
    for symbol in candidate_symbols(limit):
        df = price_frame(symbol, min_rows=int(params["min_history_days"]))
        if df.empty:
            continue
        close = close_series(df)
        turnover = pd.to_numeric(df.get("turnover", pd.Series(dtype="float64")), errors="coerce").dropna()
        amount = pd.to_numeric(df.get("amount", pd.Series(dtype="float64")), errors="coerce").dropna()
        flow_window = int(params["flow_window"])
        flow_proxy = float(turnover.tail(flow_window).mean()) if len(turnover) else float(amount.tail(flow_window).mean() if len(amount) else 0.0)
        metrics.append(
            {
                "symbol": symbol,
                "volume_ratio": volume_ratio(df, int(params["volume_window"])),
                "price_momentum": pct_return(close, int(params["momentum_window"])),
                "turnover_moneyflow_proxy": flow_proxy,
            }
        )

    volume_rank = percentile_score(pd.Series({m["symbol"]: m["volume_ratio"] for m in metrics}))
    momentum_rank = percentile_score(pd.Series({m["symbol"]: m["price_momentum"] for m in metrics}))
    flow_rank = percentile_score(pd.Series({m["symbol"]: m["turnover_moneyflow_proxy"] for m in metrics}))
    rows: list[dict] = []
    for item in metrics:
        symbol = item["symbol"]
        score = (
            volume_rank.get(symbol, 0.0) * float(weights["volume"])
            + momentum_rank.get(symbol, 0.0) * float(weights["momentum"])
            + flow_rank.get(symbol, 0.0) * float(weights["flow"])
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
                    "volume_ratio": round(item["volume_ratio"], 3),
                    "volume_rank": volume_rank.get(symbol, 0.0),
                    "price_momentum": round(item["price_momentum"], 4),
                    "momentum_rank": momentum_rank.get(symbol, 0.0),
                    "turnover_moneyflow_proxy": round(item["turnover_moneyflow_proxy"], 4),
                    "flow_rank": flow_rank.get(symbol, 0.0),
                },
            )
        )
    return selected_candidate_rows(rows, "volume_confirmation")
