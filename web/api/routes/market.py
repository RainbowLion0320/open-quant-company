"""市场数据路由"""

from fastapi import APIRouter
from datetime import datetime
import pandas as pd
import yaml
import os

router = APIRouter(prefix="/api/market", tags=["Market"])


@router.get("")
async def market_overview():
    """市场总览: regime + K线 + 策略配置"""
    from cybernetics.orchestrator import QuantOrchestrator

    orch = QuantOrchestrator()
    snapshot = orch.detect()
    params = orch.get_params()

    from data.fetcher import get_index_daily
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])
    recent = bench.tail(120)

    kline = []
    for _, row in recent.iterrows():
        kline.append({
            "date": str(row["date"])[:10],
            "close": float(row["close"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": int(row["volume"]),
        })

    from pathlib import Path
    config_path = Path(__file__).resolve().parent.parent.parent.parent / "config" / "settings.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    from data.registry import get_enabled_strategies
    from data.symbols import CIRCLE_STOCKS

    return {
        "regime": {
            "value": snapshot.regime.value,
            "ma_trend": snapshot.index_ma_trend,
            "volume_trend": snapshot.volume_trend,
            "breadth": round(snapshot.breadth, 2),
        },
        "params": params,
        "kline": kline,
        "config": {
            "buffett": cfg.get("buffett", {}),
            "cybernetics": cfg.get("cybernetics", {}),
            "multifactor": cfg.get("signals", {}).get("multifactor", {}),
            "backtest": cfg.get("backtest", {}),
            "trading": cfg.get("trading", {}),
        },
        "registry": get_enabled_strategies(),
        "pool_size": len(CIRCLE_STOCKS),
        "updated": datetime.now().strftime("%H:%M"),
    }
