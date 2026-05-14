"""模拟交易路由 — 持仓 / 资金 / 下单 / 订单"""

from fastapi import APIRouter, HTTPException
from web.api.models import OrderRequest, PositionItem, AccountInfo, OrderItem
from web.api.errors import InvalidParameterError

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])


# ── 模块级单例 PaperBroker ────────────────────────────────

_broker = None


def get_broker():
    """获取或初始化 PaperBroker 单例"""
    global _broker
    if _broker is None:
        from broker import PaperBroker
        _broker = PaperBroker(initial_cash=1_000_000, commission_rate=0.00081)
    return _broker


# ── 持仓 ──────────────────────────────────────────────────

@router.get("/positions")
async def get_positions():
    """当前持仓列表"""
    broker = get_broker()
    positions = broker.get_positions()

    return {
        "positions": [
            PositionItem(
                code=p.code,
                name=p.name,
                volume=p.volume,
                avg_cost=round(p.avg_cost, 2),
                current_price=round(p.current_price, 2),
                market_value=round(p.market_value, 2),
                pnl=round(p.pnl, 2),
                pnl_pct=round(p.pnl_pct * 100, 2),
            )
            for p in sorted(positions, key=lambda x: -x.market_value)
        ],
        "total": len(positions),
    }


# ── 资金 ──────────────────────────────────────────────────

@router.get("/balance")
async def get_balance():
    """账户资金概览"""
    broker = get_broker()
    balance = broker.get_balance()

    return AccountInfo(
        total_asset=round(balance.total_asset, 2),
        cash=round(balance.cash, 2),
        frozen_cash=round(balance.frozen_cash, 2),
        market_value=round(balance.market_value, 2),
    )


# ── 下单 ──────────────────────────────────────────────────

@router.post("/order")
async def submit_order(req: OrderRequest):
    """提交模拟订单"""
    if req.side not in ("buy", "sell"):
        raise InvalidParameterError("side", req.side, "Must be 'buy' or 'sell'")

    if req.volume <= 0:
        raise InvalidParameterError("volume", str(req.volume), "Must be positive")

    if req.price < 0:
        raise InvalidParameterError("price", str(req.price), "Must be non-negative (0=market)")

    broker = get_broker()

    # 尝试获取实时价格（当 price=0 时市价）
    if req.price <= 0:
        try:
            from data.fetcher import get_stock_daily
            df = get_stock_daily(req.code)
            if df is not None and len(df) > 0:
                current = float(df.sort_values("date").iloc[-1]["close"])
                broker.set_prices({req.code: current})
        except Exception:
            pass

    result = broker.submit_order(
        code=req.code,
        price=req.price,
        volume=req.volume,
        side=req.side,
    )

    # result 是 order_id (成功) 或错误信息 (失败)
    if result and not result.startswith("PAPER_"):
        raise HTTPException(status_code=400, detail=result)

    return {
        "order_id": result,
        "status": "filled",
        "code": req.code,
        "side": req.side,
        "volume": req.volume,
    }


# ── 订单列表 ──────────────────────────────────────────────

@router.get("/orders")
async def get_orders():
    """当日订单列表"""
    broker = get_broker()
    orders = broker.get_orders()

    return {
        "orders": [
            OrderItem(
                order_id=o.order_id,
                code=o.code,
                side=o.side,
                price=round(o.price, 2),
                volume=o.volume,
                filled_volume=o.filled_volume,
                status=o.status,
                created_at=o.created_at,
            )
            for o in reversed(orders)  # 最新在前
        ],
        "total": len(orders),
    }
