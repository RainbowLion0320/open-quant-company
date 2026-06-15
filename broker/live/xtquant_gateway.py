from __future__ import annotations

import importlib
import time
from typing import Any


DEFAULT_ACCOUNT_TYPE = "STOCK"
DEFAULT_STRATEGY_NAME = "open_quant_company"


class XtQuantGateway:
    """MiniQMT/QMT SDK gateway backed by xtquant.

    The gateway is deliberately thin: it submits orders and reads broker
    snapshots, while project-ledger matching remains a higher-level concern.
    """

    def __init__(
        self,
        *,
        config: dict[str, Any],
        account_id: str,
        broker: str,
        trader_cls: Any,
        account_cls: Any,
        constants: Any,
    ):
        self.config = dict(config)
        self.account_id = str(account_id or "").strip()
        if not self.account_id:
            raise ValueError("account_id is required")
        self.broker = str(broker or "miniqmt")
        self.userdata_path = str(self.config.get("userdata_path") or "").strip()
        if not self.userdata_path:
            raise ValueError("sdk_gateway_config.userdata_path is required")
        self.session_id = int(self.config.get("session_id") or int(time.time() * 1000))
        self.account_type = str(self.config.get("account_type") or DEFAULT_ACCOUNT_TYPE).strip()
        self.strategy_name = str(self.config.get("strategy_name") or DEFAULT_STRATEGY_NAME).strip()
        self.remark_prefix = str(self.config.get("remark_prefix") or "approval").strip()
        self.price_type_const = str(self.config.get("price_type_const") or "FIX_PRICE").strip()
        self.trader = trader_cls(self.userdata_path, self.session_id)
        self.account = _build_account(account_cls, self.account_id, self.account_type)
        self.constants = constants
        self._connected = False

    def submit_order(self, intent: dict[str, Any], *, approval_id: str, account_id: str) -> dict[str, Any]:
        self._require_account(account_id)
        self._ensure_connected()
        side = str(intent.get("side") or "").strip().lower()
        order_type = self._order_type(side)
        price_type = self._constant(self.price_type_const)
        quantity = int(intent.get("quantity") or 0)
        price = float(intent.get("limit_price") or 0.0)
        symbol = str(intent.get("symbol") or "").strip().upper()
        if not symbol:
            raise ValueError("symbol is required")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price <= 0:
            raise ValueError("limit_price must be positive")
        remark = f"{self.remark_prefix}:{approval_id}" if self.remark_prefix else str(approval_id)
        broker_order_id = self.trader.order_stock(
            self.account,
            symbol,
            order_type,
            quantity,
            price_type,
            price,
            self.strategy_name,
            remark,
        )
        if broker_order_id is None or str(broker_order_id).strip() == "":
            raise RuntimeError("xtquant order_stock returned an empty broker order id")
        return {
            "broker": self.broker,
            "broker_order_id": str(broker_order_id),
            "broker_status": "submitted",
            "account_id": self.account_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "limit_price": price,
            "price_type": self.price_type_const,
            "strategy_name": self.strategy_name,
            "order_remark": remark,
        }

    def reconcile(self, ack: dict[str, Any], *, account_id: str) -> dict[str, Any]:
        self._require_account(account_id)
        self._ensure_connected()
        account_snapshot = _to_mapping(self.trader.query_stock_asset(self.account))
        positions = _records(self.trader.query_stock_positions(self.account))
        orders = _records(self.trader.query_stock_orders(self.account))
        trades = _records(self.trader.query_stock_trades(self.account))
        broker_order_id = str(ack.get("broker_order_id") or "").strip()
        mismatches = [{"reason": "project_ledger_comparison_not_configured"}]
        if broker_order_id and not _contains_order_id([*orders, *trades], broker_order_id):
            mismatches.append({"reason": "broker_order_not_found", "broker_order_id": broker_order_id})
        return {
            "broker": self.broker,
            "account_id": self.account_id,
            "positions_matched": False,
            "cash_matched": False,
            "account_snapshot": account_snapshot,
            "positions": positions,
            "open_orders": orders,
            "fills": trades,
            "mismatches": mismatches,
        }

    def _ensure_connected(self) -> None:
        if self._connected:
            return
        start = getattr(self.trader, "start", None)
        if callable(start):
            start()
        connect = getattr(self.trader, "connect", None)
        if not callable(connect):
            raise AttributeError("xtquant trader missing connect()")
        result = connect()
        if result not in (0, None, True):
            raise RuntimeError(f"xtquant connect failed: {result}")
        subscribe = getattr(self.trader, "subscribe", None)
        if callable(subscribe):
            result = subscribe(self.account)
            if result not in (0, None, True):
                raise RuntimeError(f"xtquant subscribe failed: {result}")
        self._connected = True

    def _require_account(self, account_id: str) -> None:
        if str(account_id or "").strip() != self.account_id:
            raise ValueError("account_id does not match configured live account")

    def _order_type(self, side: str) -> Any:
        if side == "buy":
            return self._constant("STOCK_BUY")
        if side == "sell":
            return self._constant("STOCK_SELL")
        raise ValueError(f"unsupported side: {side}")

    def _constant(self, name: str) -> Any:
        if not name or not hasattr(self.constants, name):
            raise AttributeError(f"xtquant constant missing: {name}")
        return getattr(self.constants, name)


def build_gateway(*, config: dict[str, Any], account_id: str, broker: str) -> XtQuantGateway:
    xttrader = importlib.import_module("xtquant.xttrader")
    xttype = importlib.import_module("xtquant.xttype")
    xtconstant = importlib.import_module("xtquant.xtconstant")
    return XtQuantGateway(
        config=dict(config or {}),
        account_id=account_id,
        broker=broker,
        trader_cls=getattr(xttrader, "XtQuantTrader"),
        account_cls=getattr(xttype, "StockAccount"),
        constants=xtconstant,
    )


def _build_account(account_cls: Any, account_id: str, account_type: str) -> Any:
    try:
        return account_cls(account_id, account_type)
    except TypeError:
        return account_cls(account_id)


def _records(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_to_mapping(item) for item in value]
    if isinstance(value, tuple):
        return [_to_mapping(item) for item in value]
    return [_to_mapping(value)]


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    if hasattr(value, "__dict__"):
        return {str(key): item for key, item in vars(value).items() if not key.startswith("_") and not callable(item)}
    fields = {}
    for key in (
        "account_id",
        "cash",
        "total_asset",
        "market_value",
        "stock_code",
        "volume",
        "can_use_volume",
        "order_id",
        "order_sysid",
        "entrust_no",
        "order_status",
        "traded_volume",
        "traded_price",
    ):
        if hasattr(value, key):
            fields[key] = getattr(value, key)
    if fields:
        return fields
    return {"value": str(value)}


def _contains_order_id(records: list[dict[str, Any]], broker_order_id: str) -> bool:
    for record in records:
        for key in ("broker_order_id", "order_id", "order_sysid", "entrust_no", "order_ref"):
            if str(record.get(key) or "").strip() == broker_order_id:
                return True
    return False
