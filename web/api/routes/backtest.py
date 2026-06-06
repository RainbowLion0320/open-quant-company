"""回测分析路由 — 多策略对比"""

import pickle
from fastapi import APIRouter
from data.storage.datahub import get_datahub
from web.api.errors import DataNotFoundError, InvalidParameterError

router = APIRouter(prefix="/api/backtest", tags=["Backtest"])


def _load_backtest_artifact(name: str) -> dict:
    path = get_datahub().artifact_path("backtests", f"{name}.pkl")
    if path.exists():
        with open(path, "rb") as f:
            data = pickle.load(f)
        return data if isinstance(data, dict) else {}
    return {}


@router.get("")
async def backtest_overview():
    """三策略对比概览"""
    data = _load_backtest_artifact("backtest_comparison")
    if data:
        return {
            "strategies": data.get("strategies", {}),
            "bench_return": data.get("bench_return", 0),
            "start": data.get("start", ""),
            "end": data.get("end", ""),
        }

    raise DataNotFoundError("backtest results", "run backtest/run_all_strategies.py first")


@router.get("/{strategy}")
async def strategy_detail(strategy: str):
    """单个策略详细数据（净值曲线）"""
    from data.strategy.catalog import list_strategy_names
    valid = list_strategy_names()
    if strategy not in valid:
        raise InvalidParameterError("strategy", strategy, f"Choose from: {', '.join(sorted(valid))}")

    data = _load_backtest_artifact(f"backtest_{strategy}")
    if not data:
        raise DataNotFoundError("backtest results", strategy)

    daily = data.get("daily_returns")
    bench = data.get("bench_returns")

    def to_curve(returns, step=5):
        if returns is None or len(returns) == 0:
            return []
        cum = (returns + 1).cumprod() * 100
        return [
            {"date": str(d), "value": round(float(v), 2)}
            for d, v in zip(cum.index.strftime("%Y-%m-%d"), cum.values)
        ][::step]

    return {
        "total_return": data.get("total_return", 0),
        "sharpe": data.get("sharpe", 0),
        "max_drawdown": data.get("max_drawdown", 0),
        "win_rate": data.get("win_rate", 0),
        "trade_count": data.get("trade_count", 0),
        "equity_curve": to_curve(daily),
        "bench_curve": to_curve(bench),
    }
