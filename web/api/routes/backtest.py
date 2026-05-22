"""回测分析路由 — 多策略对比"""

import json
from fastapi import APIRouter
from pathlib import Path
from web.api.errors import DataNotFoundError, InvalidParameterError

router = APIRouter(prefix="/api/backtest", tags=["Backtest"])

_DATA = Path(__file__).resolve().parent.parent.parent.parent / "data"


def _safe_load(path: Path) -> dict:
    """安全加载回测结果 — 优先 JSON, fallback pickle (仅限已知文件)"""
    json_path = path.with_suffix(".json")
    if json_path.exists():
        with open(json_path) as f:
            return json.load(f)
    if path.exists() and path.suffix == ".pkl":
        import pickle
        with open(path, "rb") as f:
            return pickle.load(f)
    return {}


@router.get("")
async def backtest_overview():
    """三策略对比概览"""
    cmp_path = _DATA / "backtest_comparison.pkl"
    data = _safe_load(cmp_path)
    if data:
        return {
            "strategies": data.get("strategies", {}),
            "bench_return": data.get("bench_return", 0),
            "start": data.get("start", ""),
            "end": data.get("end", ""),
        }

    # fallback to old single-strategy result
    old = _DATA / "backtest_monthly_result.pkl"
    d = _safe_load(old)
    if d:
        return {"strategies": {"multifactor": _extract(d)}, "bench_return": d.get("bench_return", 0)}

    raise DataNotFoundError("backtest results", "run backtest/run_all_strategies.py first")


@router.get("/{strategy}")
async def strategy_detail(strategy: str):
    """单个策略详细数据（净值曲线）"""
    from data.registry import list_strategy_names
    valid = list_strategy_names()
    if strategy not in valid:
        raise InvalidParameterError("strategy", strategy, f"Choose from: {', '.join(sorted(valid))}")

    path = _DATA / f"backtest_{strategy}.pkl"
    data = _safe_load(path)
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


def _extract(d: dict) -> dict:
    return {
        "total_return": d.get("total_return", 0),
        "sharpe": d.get("sharpe", 0),
        "max_drawdown": d.get("max_drawdown", 0),
        "win_rate": d.get("win_rate", 0),
        "trade_count": d.get("trade_count", 0),
    }
