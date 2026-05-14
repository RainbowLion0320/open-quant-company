"""回测分析路由 — 多策略对比"""

from fastapi import APIRouter
import pickle
from pathlib import Path

router = APIRouter(prefix="/api/backtest", tags=["Backtest"])

_DATA = Path(__file__).resolve().parent.parent.parent.parent / "data"


@router.get("")
async def backtest_overview():
    """三策略对比概览"""
    cmp_path = _DATA / "backtest_comparison.pkl"
    if not cmp_path.exists():
        # fallback to old single-strategy result
        old = _DATA / "backtest_monthly_result.pkl"
        if old.exists():
            with open(old, "rb") as f:
                d = pickle.load(f)
            return {"strategies": {"multifactor": _extract(d)}, "bench_return": d.get("bench_return", 0)}

        return {"error": "No backtest results. Run backtest/run_all_strategies.py first."}

    with open(cmp_path, "rb") as f:
        cmp = pickle.load(f)

    return {
        "strategies": cmp.get("strategies", {}),
        "bench_return": cmp.get("bench_return", 0),
        "start": cmp.get("start", ""),
        "end": cmp.get("end", ""),
    }


@router.get("/{strategy}")
async def strategy_detail(strategy: str):
    """单个策略详细数据（净值曲线）"""
    path = _DATA / f"backtest_{strategy}.pkl"
    if not path.exists():
        return {"error": f"No backtest results for {strategy}"}

    with open(path, "rb") as f:
        data = pickle.load(f)

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
