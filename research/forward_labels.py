"""Shared forward-window label builders for regime research."""
from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def future_compound_return(returns: pd.Series, pos: int, horizon: int) -> float:
    window = returns.iloc[pos + 1 : pos + horizon + 1].dropna()
    if len(window) < horizon:
        return np.nan
    return float((1.0 + window).prod() - 1.0)


def future_price_window_metrics(
    close: pd.Series,
    horizons: Iterable[int] = (5, 20, 60),
) -> pd.DataFrame:
    close = close.sort_index().astype(float)
    out = pd.DataFrame(index=close.index)
    for horizon in horizons:
        future = close.shift(-horizon)
        out[f"future_{horizon}d_return"] = (future - close) / close
        drawdowns = []
        volatilities = []
        for pos in range(len(close)):
            window = close.iloc[pos + 1 : pos + horizon + 1]
            if len(window) < horizon:
                drawdowns.append(np.nan)
                volatilities.append(np.nan)
                continue
            start = close.iloc[pos]
            path = window / start - 1.0
            drawdowns.append(float(min(0.0, path.min())))
            returns = window.pct_change().dropna()
            volatilities.append(float(returns.std() * np.sqrt(252)) if len(returns) else np.nan)
        out[f"future_{horizon}d_max_drawdown"] = drawdowns
        out[f"future_{horizon}d_volatility"] = volatilities
    return out


def build_forward_labels(close: pd.Series, horizons: Iterable[int] = (5, 20, 60)) -> pd.DataFrame:
    out = future_price_window_metrics(close, horizons)
    if "future_20d_max_drawdown" in out:
        out["bear_event_next_20d"] = out["future_20d_max_drawdown"] <= -0.08
    if "future_20d_return" in out:
        out["bull_continuation_next_20d"] = out["future_20d_return"] >= 0.03
    return out


def build_profit_labels(asset_panel: pd.DataFrame, horizons: Iterable[int] = (5, 20, 60)) -> pd.DataFrame:
    panel = asset_panel.sort_index().copy()
    labels = pd.DataFrame(index=panel.index)
    close = panel["equity_close"].astype(float)
    equity_returns = panel["equity_return"].astype(float)
    cash_returns = panel["cash_return"].astype(float)
    defensive_returns = panel["defensive_return"].astype(float)

    for horizon in horizons:
        equity_forward = []
        cash_forward = []
        defensive_forward = []
        drawdowns = []
        volatilities = []
        for pos in range(len(panel)):
            equity_ret = future_compound_return(equity_returns, pos, horizon)
            cash_ret = future_compound_return(cash_returns, pos, horizon)
            defensive_ret = future_compound_return(defensive_returns, pos, horizon)
            equity_forward.append(equity_ret)
            cash_forward.append(cash_ret)
            defensive_forward.append(defensive_ret)

            path = close.iloc[pos + 1 : pos + horizon + 1]
            if len(path) < horizon:
                drawdowns.append(np.nan)
                volatilities.append(np.nan)
                continue
            relative_path = path / close.iloc[pos] - 1.0
            drawdowns.append(float(min(0.0, relative_path.min())))
            realized = equity_returns.iloc[pos + 1 : pos + horizon + 1].dropna()
            volatilities.append(float(realized.std(ddof=1) * np.sqrt(252)) if len(realized) > 1 else 0.0)

        labels[f"future_{horizon}d_equity_return"] = equity_forward
        labels[f"future_{horizon}d_equity_max_drawdown"] = drawdowns
        labels[f"future_{horizon}d_equity_volatility"] = volatilities
        labels[f"future_{horizon}d_cash_excess_return"] = labels[f"future_{horizon}d_equity_return"] - pd.Series(cash_forward, index=labels.index)
        labels[f"future_{horizon}d_defensive_excess_return"] = labels[f"future_{horizon}d_equity_return"] - pd.Series(defensive_forward, index=labels.index)

    if "future_20d_equity_return" in labels:
        labels["risk_on_profitable_next_20d"] = (
            (labels["future_20d_equity_return"] > 0.0)
            & (labels["future_20d_cash_excess_return"] > 0.0)
            & (labels["future_20d_defensive_excess_return"] > 0.0)
        )
        labels["risk_off_preferred_next_20d"] = (
            (labels["future_20d_equity_return"] < 0.0)
            | (labels["future_20d_defensive_excess_return"] < 0.0)
            | (labels["future_20d_equity_max_drawdown"] <= -0.08)
        )
    return labels
