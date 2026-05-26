import importlib

import pytest
import yaml


def _risk_config(tmp_path, active_rule: str, rule_config: dict):
    all_rules = {
        "max_single_position": {"enabled": False},
        "max_total_exposure": {"enabled": False},
        "max_orders_per_day": {"enabled": False},
        "max_drawdown_circuit_breaker": {"enabled": False},
        "max_single_order_amount": {"enabled": False},
    }
    all_rules[active_rule] = {"enabled": True, **rule_config}
    path = tmp_path / f"{active_rule}.yaml"
    path.write_text(yaml.safe_dump({"risk_control": all_rules}), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("rule_name", "rule_config", "amount", "portfolio", "expected_reason"),
    [
        (
            "max_single_position",
            {"max_pct": 0.20},
            25_000,
            {"total_equity": 100_000, "total_exposure": 0, "peak_equity": 100_000, "positions": {}},
            "仓位",
        ),
        (
            "max_total_exposure",
            {"max_pct": 0.50},
            15_000,
            {"total_equity": 100_000, "total_exposure": 45_000, "peak_equity": 100_000, "positions": {}},
            "总敞口",
        ),
        (
            "max_drawdown_circuit_breaker",
            {"max_drawdown_pct": -0.10},
            1_000,
            {"total_equity": 85_000, "total_exposure": 0, "peak_equity": 100_000, "positions": {}},
            "熔断",
        ),
        (
            "max_single_order_amount",
            {"max_amount": 5_000},
            5_001,
            {"total_equity": 100_000, "total_exposure": 0, "peak_equity": 100_000, "positions": {}},
            "订单金额",
        ),
    ],
)
def test_risk_manager_rejects_each_configured_limit(tmp_path, rule_name, rule_config, amount, portfolio, expected_reason):
    from broker.risk import RiskManager

    risk = RiskManager(config_path=_risk_config(tmp_path, rule_name, rule_config))
    passed, results = risk.check_order("000001", amount, portfolio)

    assert not passed
    assert results[-1].rule_name == rule_name
    assert expected_reason in results[-1].reason


def test_risk_manager_enforces_daily_order_count(tmp_path):
    from broker.risk import RiskManager

    risk = RiskManager(config_path=_risk_config(tmp_path, "max_orders_per_day", {"max_count": 1}))
    portfolio = {"total_equity": 100_000, "total_exposure": 0, "peak_equity": 100_000, "positions": {}}

    passed, _ = risk.check_order("000001", 1_000, portfolio)
    assert passed

    risk.record_order()
    passed, results = risk.check_order("000002", 1_000, portfolio)
    assert not passed
    assert results[-1].rule_name == "max_orders_per_day"


def test_paper_state_persistence_round_trip_uses_public_state_model(tmp_path, monkeypatch):
    from data.datahub import reset_datahub
    from broker.state import PaperBrokerState

    monkeypatch.setenv("ASTROLABE_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("ASTROLABE_CACHE", str(tmp_path / "cache"))
    reset_datahub()

    import broker.persistence as persistence

    persistence = importlib.reload(persistence)
    state = PaperBrokerState(
        cash=88_000,
        frozen_cash=100,
        peak_equity=120_000,
        order_counter=7,
        positions={"000001": {"volume": 300, "avg_cost": 10.5, "name": "平安银行", "current_price": 11.0}},
    )

    persistence.save_state(state)
    loaded = persistence.load_state()

    assert loaded.cash == 88_000
    assert loaded.frozen_cash == 100
    assert loaded.peak_equity == 120_000
    assert loaded.order_counter == 7
    assert loaded.positions["000001"]["volume"] == 300
    assert loaded.positions["000001"]["current_price"] == 11.0
    reset_datahub()


def test_asset_allocator_normalizes_regime_enum_and_unknown(tmp_path):
    from broker.allocator import AssetAllocator
    from cybernetics.regime import MarketRegime

    config = tmp_path / "settings.yaml"
    config.write_text("asset_allocation: {}\n", encoding="utf-8")
    allocator = AssetAllocator(config_path=config)

    assert allocator.get_weights(MarketRegime.BEAR)["bond"] == pytest.approx(0.40)
    assert allocator.get_weights("invalid-regime")["cash"] == pytest.approx(0.35)

    allocation = allocator.allocate(
        MarketRegime.BULL,
        enabled_assets={"stock": True, "etf": True},
        asset_signals={
            "stock": [{"symbol": "000001", "score": 90}, {"symbol": "000002", "score": 80}],
            "etf": [{"symbol": "510300", "score": 70}],
        },
        total_capital=100_000,
        max_positions_per_asset=1,
    )

    assert allocation.regime == "bull"
    assert [a.asset_type for a in allocation.allocations] == ["stock", "etf"]
    assert allocation.allocations[0].symbols == ["000001"]


def test_exchange_costs_are_asset_specific():
    from broker.exchange import AShareExchange, ETFExchange, OrderSide

    stock = AShareExchange(commission=0.00025, stamp_tax=0.0005, transfer_fee=0.00001)
    etf = ETFExchange(commission=0.00005)

    stock_sell_cost = stock.calc_cost(price=10, shares=10_000, side=OrderSide.SELL)
    stock_buy_cost = stock.calc_cost(price=10, shares=10_000, side=OrderSide.BUY)
    etf_sell_cost = etf.calc_cost(price=10, shares=10_000, side=OrderSide.SELL)

    assert stock_sell_cost > stock_buy_cost
    assert etf_sell_cost < stock_sell_cost
