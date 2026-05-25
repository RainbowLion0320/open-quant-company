import importlib
from pathlib import Path

import numpy as np
import pandas as pd


def test_build_features_import_is_safe():
    module = importlib.import_module("scripts.build_features")
    assert callable(module.build_features)
    assert callable(module.rebuild_recent)


def test_rebuild_recent_targets_completed_months():
    module = importlib.import_module("scripts.build_features")
    assert module._recent_month_window(3, pd.Timestamp("2026-05-18")) == ("2026-02", "2026-04")


def test_model_evaluate_datetime_index_icir_does_not_crash():
    from models import BaseModel

    class DummyModel(BaseModel):
        def predict(self, X):
            return np.arange(len(X), dtype=float)

    X = pd.DataFrame({"x": range(8)}, index=pd.date_range("2024-01-01", periods=8, freq="D"))
    y = pd.Series(range(8), index=X.index)
    result = DummyModel().evaluate(X, y)
    assert result["ic"] > 0
    assert "icir" in result


def test_prepare_xy_drops_missing_targets():
    from models import prepare_xy

    df = pd.DataFrame(
        {
            "symbol": ["A", "B", "C"],
            "factor": [1.0, None, 3.0],
            "ret_fwd_20d": [0.1, None, -0.2],
        }
    )
    X, y = prepare_xy(df)
    assert len(X) == 2
    assert len(y) == 2
    assert X["factor"].isna().sum() == 0


def test_paper_broker_never_sells_more_than_position_when_t0():
    from broker import PaperBroker

    broker = PaperBroker(initial_cash=100000, t_plus_1=False, enable_risk=False)
    broker.set_prices({"000001": 10.0})
    assert broker.submit_order("000001", price=10.0, volume=100, side="buy").startswith("PAPER_")
    assert broker.submit_order("000001", price=10.0, volume=300, side="sell").startswith("PAPER_")
    broker.end_of_day()
    assert broker.get_positions() == []


def test_paper_broker_is_exported_from_dedicated_module():
    import broker
    from broker.paper import PaperBroker

    assert broker.PaperBroker is PaperBroker


def test_paper_broker_state_round_trips_through_public_api():
    from broker import PaperBroker
    from broker.state import PaperBrokerState

    state = PaperBrokerState(
        cash=12345.0,
        frozen_cash=25.0,
        peak_equity=15000.0,
        order_counter=42,
        positions={
            "000001": {
                "name": "平安银行",
                "volume": 200,
                "avg_cost": 8.5,
                "current_price": 9.1,
            }
        },
    )

    broker = PaperBroker.from_state(state, enable_risk=False)

    balance = broker.get_balance()
    assert balance.cash == 12345.0
    assert balance.frozen_cash == 25.0
    assert broker.get_position("000001").volume == 200
    assert broker.get_position_codes() == ["000001"]

    restored = broker.snapshot_state()
    assert restored.cash == 12345.0
    assert restored.peak_equity == 15000.0
    assert restored.order_counter == 42
    assert restored.positions["000001"]["avg_cost"] == 8.5


def test_paper_broker_private_state_is_not_used_outside_broker_package():
    forbidden = (
        "broker._cash",
        "broker._frozen_cash",
        "broker._positions",
        "broker._order_counter",
        "broker._today_buys",
        "broker._today_sells",
        "broker._peak_equity",
    )
    checked_files = [
        Path("scripts/execute_paper_trades.py"),
        Path("web/api/routes/portfolio.py"),
    ]

    offenders = []
    for path in checked_files:
        text = path.read_text()
        offenders.extend(f"{path}:{token}" for token in forbidden if token in text)

    assert offenders == []


def test_enabled_strategy_plugins_have_runners():
    from data.strategy_plugins import iter_strategy_plugins

    plugins = list(iter_strategy_plugins("all"))
    assert plugins
    for plugin in plugins:
        assert callable(plugin.load_runner())


def test_datahub_catalog_includes_data_registry_dimensions():
    from data.datahub import get_datahub

    catalog = get_datahub().catalog()
    assert "signals" in catalog
    assert any(key.startswith("dimension:") for key in catalog)


def test_stock_daily_read_path_does_not_implicitly_fetch_api(monkeypatch):
    from data import fetcher
    import data.fetchers.stock_daily as stock_daily

    monkeypatch.delenv("QUANT_ALLOW_API_FALLBACK", raising=False)

    def fail_fetch(*args, **kwargs):
        raise AssertionError("API fetch should not be called by default")

    monkeypatch.setattr(stock_daily, "fetch_one", fail_fetch)
    df = fetcher.get_stock_daily("999998")
    assert df.empty


def test_repairable_tables_are_sourced_from_repair_map():
    from scripts.repair_table import REPAIR_MAP
    from web.api.routes.system import _repairable_tables

    assert _repairable_tables() == set(REPAIR_MAP)
    assert "stock_moneyflow_daily" in _repairable_tables()


def test_system_route_delegates_large_status_domains_to_services():
    import web.api.services.system_data_health as data_health
    import web.api.services.system_integrations as integrations
    import web.api.services.system_monitor as monitor

    route_text = Path("web/api/routes/system.py").read_text()

    assert callable(monitor.system_monitor_payload)
    assert callable(data_health.db_health_payload)
    assert callable(integrations.service_status_payload)
    assert "def _query(" not in route_text
    assert "def _read_token(" not in route_text
    assert "def _run_repair(" not in route_text
    assert "def _repairable_tables(" not in route_text


def test_scripts_do_not_import_regime_helpers_from_orchestrator():
    checked_files = [
        Path("scripts/multi_asset_tournament.py"),
        Path("scripts/train_regime_models.py"),
    ]

    offenders = []
    for path in checked_files:
        text = path.read_text()
        if "from cybernetics.orchestrator import detect_market_regime" in text:
            offenders.append(str(path))
        if "from cybernetics.orchestrator import MarketRegime" in text:
            offenders.append(str(path))

    assert offenders == []
