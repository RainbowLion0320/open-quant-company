"""模拟交易路由 — 持仓 / 资金 / 下单 / NAV / 交易历史

所有数据从 broker/persistence.py 持久化状态读取。
PaperBroker 实例从 Parquet 恢复，确保服务器重启不丢状态。
"""

from fastapi import APIRouter, HTTPException
from web.api.models import OrderRequest, PositionItem, AccountInfo, OrderItem
from web.api.errors import InvalidParameterError

router = APIRouter(prefix="/api/portfolio", tags=["Portfolio"])

# ── 模块级单例 PaperBroker ────────────────────────────────

_broker = None


def get_broker():
    """获取或初始化 PaperBroker 单例。从持久化状态恢复。"""
    global _broker
    if _broker is None:
        from broker import PaperBroker
        from broker.persistence import load_state

        state = load_state()
        broker = PaperBroker(
            initial_cash=1_000_000,
            commission_rate=0.00081,
            t_plus_1=True,
            enable_risk=True,
        )
        # 恢复状态
        broker._cash = state.cash
        broker._frozen_cash = state.frozen_cash
        broker._peak_equity = state.peak_equity
        broker._order_counter = state.order_counter

        from broker import Position
        for code, pos_data in state.positions.items():
            broker._positions[code] = Position(
                code=code,
                name=pos_data.get("name", ""),
                volume=pos_data["volume"],
                avg_cost=pos_data["avg_cost"],
            )
        _broker = broker
    return _broker


def refresh_broker():
    """强制重新从 Parquet 加载状态 (用于手动执行后刷新)"""
    global _broker
    _broker = None
    return get_broker()


# ── 持仓 ──────────────────────────────────────────────────


@router.get("/positions")
async def get_positions():
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


@router.get("/balance", response_model=AccountInfo)
async def get_balance():
    broker = get_broker()
    balance = broker.get_balance()

    return AccountInfo(
        total_asset=round(balance.total_asset, 2),
        cash=round(balance.cash, 2),
        frozen_cash=round(balance.frozen_cash, 2),
        market_value=round(balance.market_value, 2),
    )


# ── NAV 历史 ──────────────────────────────────────────────


@router.get("/nav")
async def get_nav_history():
    """NAV 历史净值 (用于权益曲线图)"""
    from broker.persistence import load_nav
    df = load_nav()
    if df.empty:
        return {"nav": []}

    df = df.sort_values("date")
    return {
        "nav": [
            {
                "date": str(row["date"])[:10],
                "total_asset": round(float(row["total_asset"]), 2),
                "cash": round(float(row["cash"]), 2),
                "market_value": round(float(row["market_value"]), 2),
            }
            for _, row in df.iterrows()
        ]
    }


# ── 交易历史 ──────────────────────────────────────────────


@router.get("/trades")
async def get_trades(limit: int = 50):
    """交易历史记录"""
    from broker.persistence import load_trades
    df = load_trades()
    if df.empty:
        return {"trades": [], "total": 0}

    df = df.sort_values("date", ascending=False)
    return {
        "trades": [
            {
                "date": str(row["date"])[:10],
                "code": str(row["code"]),
                "name": str(row.get("name", "")),
                "side": str(row["side"]),
                "price": round(float(row["price"]), 2),
                "volume": int(row["volume"]),
                "amount": round(float(row["amount"]), 2),
                "strategy": str(row.get("strategy", "")),
            }
            for _, row in df.head(limit).iterrows()
        ],
        "total": len(df),
    }


# ── 账户摘要 ──────────────────────────────────────────────


@router.get("/summary")
async def get_summary():
    """账户摘要: 资金 + 持仓 + 收益统计"""
    broker = get_broker()
    balance = broker.get_balance()
    positions = broker.get_positions()

    from broker.persistence import load_nav, load_state
    nav_df = load_nav()
    state = load_state()

    total_return = 0.0
    total_return_pct = 0.0
    if not nav_df.empty:
        initial = 1_000_000.0
        current = balance.total_asset
        total_return = current - initial
        total_return_pct = (current / initial - 1) * 100 if initial > 0 else 0

    return {
        "balance": AccountInfo(
            total_asset=round(balance.total_asset, 2),
            cash=round(balance.cash, 2),
            frozen_cash=round(balance.frozen_cash, 2),
            market_value=round(balance.market_value, 2),
        ),
        "total_return": round(total_return, 2),
        "total_return_pct": round(total_return_pct, 2),
        "positions_count": len(positions),
        "position_value": round(balance.market_value, 2),
        "peak_equity": round(state.peak_equity, 2),
        "nav_days": len(nav_df),
    }


# ── 下单 ──────────────────────────────────────────────────


@router.post("/order")
async def submit_order(req: OrderRequest):
    if req.side not in ("buy", "sell"):
        raise InvalidParameterError("side", req.side, "Must be 'buy' or 'sell'")
    if req.volume <= 0:
        raise InvalidParameterError("volume", str(req.volume), "Must be positive")
    if req.price < 0:
        raise InvalidParameterError("price", str(req.price), "Must be non-negative (0=market)")

    broker = get_broker()

    # 市价单: 尝试获取行情
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
        code=req.code, price=req.price, volume=req.volume, side=req.side,
    )

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
            for o in reversed(orders)
        ],
        "total": len(orders),
    }


# ── 刷新状态 ──────────────────────────────────────────────


@router.post("/refresh")
async def refresh_state():
    """强制从 Parquet 重新加载状态 (手动执行交易后调用)"""
    refresh_broker()
    return {"status": "ok", "message": "状态已从持久化存储刷新"}
