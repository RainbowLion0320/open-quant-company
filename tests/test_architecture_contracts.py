import importlib

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
