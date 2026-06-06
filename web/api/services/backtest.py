"""Backtest artifact payload builders for API routes."""

from __future__ import annotations

import pickle

from web.api.errors import DataNotFoundError, InvalidParameterError


def _load_backtest_artifact(name: str) -> dict:
    from data.storage.datahub import get_datahub

    path = get_datahub().artifact_path("backtests", f"{name}.pkl")
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        data = pickle.load(f)
    return data if isinstance(data, dict) else {}


def backtest_overview_payload() -> dict:
    data = _load_backtest_artifact("backtest_comparison")
    if not data:
        raise DataNotFoundError("backtest results", "run backtest/run_all_strategies.py first")
    return {
        "strategies": data.get("strategies", {}),
        "bench_return": data.get("bench_return", 0),
        "start": data.get("start", ""),
        "end": data.get("end", ""),
    }


def strategy_detail_payload(strategy: str) -> dict:
    from data.strategy.catalog import list_strategy_names

    valid = list_strategy_names()
    if strategy not in valid:
        raise InvalidParameterError("strategy", strategy, f"Choose from: {', '.join(sorted(valid))}")

    data = _load_backtest_artifact(f"backtest_{strategy}")
    if not data:
        raise DataNotFoundError("backtest results", strategy)

    return {
        "total_return": data.get("total_return", 0),
        "sharpe": data.get("sharpe", 0),
        "max_drawdown": data.get("max_drawdown", 0),
        "win_rate": data.get("win_rate", 0),
        "trade_count": data.get("trade_count", 0),
        "equity_curve": _to_curve(data.get("daily_returns")),
        "bench_curve": _to_curve(data.get("bench_returns")),
    }


def _to_curve(returns, step: int = 5) -> list[dict[str, object]]:
    if returns is None or len(returns) == 0:
        return []
    cumulative = (returns + 1).cumprod() * 100
    return [
        {"date": str(date), "value": round(float(value), 2)}
        for date, value in zip(cumulative.index.strftime("%Y-%m-%d"), cumulative.values)
    ][::step]
