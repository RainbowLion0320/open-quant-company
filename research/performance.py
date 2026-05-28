"""Shared portfolio performance metrics for research and training workflows."""
from __future__ import annotations

import numpy as np
import pandas as pd

from backtest.analytics import RiskAnalytics


def clean_daily_returns(daily_return: pd.Series) -> pd.Series:
    return daily_return.astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def portfolio_metrics(
    daily_return: pd.Series,
    *,
    periods_per_year: int = 252,
    turnover_proxy: float = 0.0,
    include_series: bool = True,
) -> dict[str, float | pd.Series]:
    """Compute the canonical research portfolio metrics from daily returns."""
    returns = clean_daily_returns(daily_return)
    equity_curve = (1.0 + returns).cumprod()
    if len(returns) < 10:
        metrics: dict[str, float | pd.Series] = {
            "cagr": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "calmar": 0.0,
            "turnover_proxy": round(float(turnover_proxy), 6),
        }
        if include_series:
            metrics.update({"daily_return": returns, "equity_curve": equity_curve})
        return metrics

    report = RiskAnalytics.compute(returns, risk_free=0.0, periods_per_year=periods_per_year)
    metrics = {
        "cagr": round(float(report.annual_return), 6),
        "sharpe": round(float(report.sharpe), 6),
        "max_drawdown": round(float(report.max_drawdown), 6),
        "calmar": round(float(report.calmar), 6),
        "turnover_proxy": round(float(turnover_proxy), 6),
    }
    if include_series:
        metrics.update({"daily_return": returns, "equity_curve": equity_curve})
    return metrics
