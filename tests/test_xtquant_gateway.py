from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest


def _install_fake_xtquant(monkeypatch):
    class FakeAccount:
        def __init__(self, account_id, account_type="STOCK"):
            self.account_id = account_id
            self.account_type = account_type

    class FakeTrader:
        instances = []

        def __init__(self, userdata_path, session_id):
            self.userdata_path = userdata_path
            self.session_id = session_id
            self.started = False
            self.connected = False
            self.subscribed = []
            self.orders = []
            FakeTrader.instances.append(self)

        def start(self):
            self.started = True

        def connect(self):
            self.connected = True
            return 0

        def subscribe(self, account):
            self.subscribed.append(account)
            return 0

        def order_stock(self, *args):
            self.orders.append(args)
            return 8848

        def query_stock_asset(self, account):
            return SimpleNamespace(account_id=account.account_id, cash=100000.0, total_asset=120000.0)

        def query_stock_positions(self, account):
            return [SimpleNamespace(stock_code="600000.SH", volume=100, account_id=account.account_id)]

        def query_stock_orders(self, account):
            return [SimpleNamespace(order_id="8848", stock_code="600000.SH", order_status="accepted")]

        def query_stock_trades(self, account):
            return [SimpleNamespace(order_id="8848", stock_code="600000.SH", traded_volume=100)]

    xtquant = types.ModuleType("xtquant")
    xttrader = types.ModuleType("xtquant.xttrader")
    xttype = types.ModuleType("xtquant.xttype")
    xtconstant = types.ModuleType("xtquant.xtconstant")
    xttrader.XtQuantTrader = FakeTrader
    xttype.StockAccount = FakeAccount
    xtconstant.STOCK_BUY = 23
    xtconstant.STOCK_SELL = 24
    xtconstant.FIX_PRICE = 11
    xtquant.xttrader = xttrader
    xtquant.xttype = xttype
    xtquant.xtconstant = xtconstant
    monkeypatch.setitem(sys.modules, "xtquant", xtquant)
    monkeypatch.setitem(sys.modules, "xtquant.xttrader", xttrader)
    monkeypatch.setitem(sys.modules, "xtquant.xttype", xttype)
    monkeypatch.setitem(sys.modules, "xtquant.xtconstant", xtconstant)
    return FakeTrader


def test_xtquant_gateway_submits_order_through_xtquant_sdk(monkeypatch):
    fake_trader_cls = _install_fake_xtquant(monkeypatch)

    from broker.live.xtquant_gateway import build_gateway

    gateway = build_gateway(
        config={
            "userdata_path": "/tmp/qmt-userdata",
            "session_id": 42,
            "strategy_name": "open_quant_company",
            "remark_prefix": "approval",
        },
        account_id="1234567890",
        broker="miniqmt",
    )
    ack = gateway.submit_order(
        {
            "symbol": "600000.SH",
            "side": "buy",
            "quantity": 100,
            "limit_price": 10.0,
            "strategy": "manual",
        },
        approval_id="approval_1",
        account_id="1234567890",
    )

    trader = fake_trader_cls.instances[0]
    assert trader.userdata_path == "/tmp/qmt-userdata"
    assert trader.session_id == 42
    assert trader.started is True
    assert trader.connected is True
    assert trader.subscribed[0].account_id == "1234567890"
    assert trader.orders == [
        (
            trader.subscribed[0],
            "600000.SH",
            23,
            100,
            11,
            10.0,
            "open_quant_company",
            "approval:approval_1",
        )
    ]
    assert ack["broker_order_id"] == "8848"
    assert ack["broker_status"] == "submitted"
    assert ack["account_id"] == "1234567890"
    assert ack["broker"] == "miniqmt"


def test_xtquant_gateway_reconcile_returns_snapshot_without_fake_match(monkeypatch):
    _install_fake_xtquant(monkeypatch)

    from broker.live.xtquant_gateway import build_gateway

    gateway = build_gateway(
        config={"userdata_path": "/tmp/qmt-userdata", "session_id": 43},
        account_id="1234567890",
        broker="miniqmt",
    )
    report = gateway.reconcile({"broker_order_id": "8848"}, account_id="1234567890")

    assert report["positions_matched"] is False
    assert report["cash_matched"] is False
    assert report["open_orders"][0]["order_id"] == "8848"
    assert report["fills"][0]["traded_volume"] == 100
    assert report["positions"][0]["stock_code"] == "600000.SH"
    assert report["account_snapshot"]["cash"] == 100000.0
    assert report["mismatches"] == [{"reason": "project_ledger_comparison_not_configured"}]
    assert report["broker"] == "miniqmt"


def test_xtquant_gateway_reconcile_matches_project_ledger_snapshot(monkeypatch):
    _install_fake_xtquant(monkeypatch)

    from broker.live.xtquant_gateway import build_gateway

    gateway = build_gateway(
        config={"userdata_path": "/tmp/qmt-userdata", "session_id": 44},
        account_id="1234567890",
        broker="miniqmt",
    )
    report = gateway.reconcile(
        {
            "broker_order_id": "8848",
            "project_snapshot": {
                "cash": 100000.0,
                "positions": [{"symbol": "600000.SH", "quantity": 100}],
                "orders": [{"broker_order_id": "8848"}],
            },
        },
        account_id="1234567890",
    )

    assert report["status"] == "matched"
    assert report["positions_matched"] is True
    assert report["cash_matched"] is True
    assert report["orders_matched"] is True
    assert report["mismatches"] == []
    assert report["project_snapshot"]["cash"] == 100000.0


def test_xtquant_gateway_reconcile_requires_complete_project_ledger_snapshot(monkeypatch):
    _install_fake_xtquant(monkeypatch)

    from broker.live.xtquant_gateway import build_gateway

    gateway = build_gateway(
        config={"userdata_path": "/tmp/qmt-userdata", "session_id": 46},
        account_id="1234567890",
        broker="miniqmt",
    )
    report = gateway.reconcile(
        {
            "broker_order_id": "8848",
            "project_snapshot": {
                "cash": 100000.0,
                "orders": [{"broker_order_id": "8848"}],
            },
        },
        account_id="1234567890",
    )

    reasons = {item["reason"] for item in report["mismatches"]}
    assert report["status"] == "needs_review"
    assert report["cash_matched"] is True
    assert report["positions_matched"] is False
    assert report["orders_matched"] is True
    assert "project_positions_not_provided" in reasons


def test_xtquant_gateway_reconcile_reports_project_ledger_mismatches(monkeypatch):
    _install_fake_xtquant(monkeypatch)

    from broker.live.xtquant_gateway import build_gateway

    gateway = build_gateway(
        config={"userdata_path": "/tmp/qmt-userdata", "session_id": 45},
        account_id="1234567890",
        broker="miniqmt",
    )
    report = gateway.reconcile(
        {
            "broker_order_id": "8848",
            "project_snapshot": {
                "cash": 90000.0,
                "positions": [{"symbol": "600000.SH", "quantity": 80}],
                "orders": [{"broker_order_id": "MISSING"}],
            },
        },
        account_id="1234567890",
    )

    reasons = {item["reason"] for item in report["mismatches"]}
    assert report["status"] == "needs_review"
    assert report["positions_matched"] is False
    assert report["cash_matched"] is False
    assert report["orders_matched"] is False
    assert {"cash_mismatch", "position_mismatch", "project_order_not_found_at_broker"} <= reasons


def test_xtquant_gateway_requires_userdata_path(monkeypatch):
    _install_fake_xtquant(monkeypatch)

    from broker.live.xtquant_gateway import build_gateway

    with pytest.raises(ValueError, match="userdata_path"):
        build_gateway(config={}, account_id="1234567890", broker="miniqmt")


def test_xtquant_gateway_validates_terminal_environment_without_submitting(monkeypatch):
    fake_trader_cls = _install_fake_xtquant(monkeypatch)

    from broker.live.xtquant_gateway import build_gateway

    gateway = build_gateway(
        config={"userdata_path": "/tmp/qmt-userdata", "session_id": 77},
        account_id="1234567890",
        broker="miniqmt",
    )

    validation = gateway.validate_environment(account_id="1234567890")

    trader = fake_trader_cls.instances[0]
    assert trader.started is True
    assert trader.connected is True
    assert trader.subscribed[0].account_id == "1234567890"
    assert trader.orders == []
    assert validation["status"] == "validated"
    assert validation["broker"] == "miniqmt"
    assert validation["account_id"] == "1234567890"
    assert validation["account_snapshot"]["cash"] == 100000.0
    assert validation["position_count"] == 1
    assert validation["open_order_count"] == 1
    assert validation["trade_count"] == 1
