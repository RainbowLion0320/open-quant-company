"""信号历史路由 — 信号变化追踪"""

from fastapi import APIRouter, Query
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/signals", tags=["Signals"])


@router.get("/changes")
async def get_signal_changes(days: int = Query(default=7, description="最近 N 天的信号变化")):
    """
    追踪策略信号变化 — 比较连续日期，找出 buy↔hold↔sell 变更的股票。

    注意: 当前 strategy_signals 表只存最新一次快照，不存历史。
    此端点通过对比 buffett_scan + strategy_signals 交叉分析来模拟变化检测。
    实际效果：列出当前信号为 buy 且最近更新的股票，作为「近期信号」展示。
    """
    from data.storage.results_db import load_strategy_signals, list_strategies, load_buffett_results

    strategies = list_strategies()
    all_signals = []

    for s in strategies:
        name = s["name"]
        signals = load_strategy_signals(name, sort="score", order="desc")
        last_computed = s.get("last_computed", "")

        for sig in signals:
            if sig.get("signal") == "buy":
                all_signals.append({
                    "date": last_computed[:10] if last_computed else "",
                    "strategy": name,
                    "symbol": sig["symbol"],
                    "name": sig.get("name", ""),
                    "from_signal": "hold",  # 近似: 从 hold 变为 buy
                    "to_signal": "buy",
                    "score": sig.get("score", 0),
                })

    # 按日期倒序，限制 days 窗口
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [s for s in all_signals if s["date"] >= cutoff or not s["date"]]

    return {
        "changes": sorted(recent, key=lambda x: x.get("score", 0) or 0, reverse=True),
        "total": len(recent),
        "window_days": days,
        "note": "Shows current buy signals within the window. Full change tracking requires historical snapshots.",
    }
