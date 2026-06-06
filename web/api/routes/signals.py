"""信号历史路由 — 信号变化追踪"""

from fastapi import APIRouter, Query
from web.api.services.signals import signal_changes_payload

router = APIRouter(prefix="/api/signals", tags=["Signals"])


@router.get("/changes")
async def get_signal_changes(days: int = Query(default=7, description="最近 N 天的信号变化")):
    """
    追踪策略信号变化 — 比较连续日期，找出 buy↔hold↔sell 变更的股票。

    注意: 当前 strategy_signals 表只存最新一次快照，不存历史。
    此端点通过对比 buffett_scan + strategy_signals 交叉分析来模拟变化检测。
    实际效果：列出当前信号为 buy 且最近更新的股票，作为「近期信号」展示。
    """
    return signal_changes_payload(days)
