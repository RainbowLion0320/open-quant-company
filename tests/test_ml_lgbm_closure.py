from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd


class DummyModel:
    def __init__(self, value: float | None = None):
        self._model = object()
        self._feature_names = ["ret_20d"]
        self.value = value

    def predict(self, frame):
        if self.value is not None:
            return [self.value for _ in range(len(frame))]
        if len(frame.columns):
            return frame.iloc[:, 0].astype(float).tolist()
        return [0.0 for _ in range(len(frame))]


class CountingModel(DummyModel):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def predict(self, frame):
        self.calls += 1
        return super().predict(frame)


class FailingPredictModel(DummyModel):
    def predict(self, frame):
        raise RuntimeError("predict failed")


class NumericOnlyModel(DummyModel):
    def predict(self, frame):
        if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in frame.dtypes):
            raise RuntimeError("non-numeric feature dtype")
        return [0.2 for _ in range(len(frame))]


def test_ml_strategy_records_model_load_errors_without_crashing(tmp_path, monkeypatch):
    import backtest.strategies.ml_strategy as ml_strategy

    (tmp_path / "lgbm_best.pkl").write_bytes(b"broken")
    (tmp_path / "lgbm_best_meta.json").write_text('{"features":["ret_20d"]}', encoding="utf-8")
    monkeypatch.setattr(ml_strategy, "MODEL_DIR", tmp_path)

    def broken_load(_file):
        raise ModuleNotFoundError("No module named 'lightgbm'")

    monkeypatch.setattr(pickle, "load", broken_load)

    strategy = ml_strategy.MLStrategy("best")

    assert strategy.is_ready is False
    assert any("lightgbm" in err for err in strategy.load_errors)


def test_ml_strategy_loads_legacy_regime_model_filename(tmp_path, monkeypatch):
    import backtest.strategies.ml_strategy as ml_strategy

    (tmp_path / "lgbm_lgbm_bull.pkl").write_bytes(b"legacy")
    (tmp_path / "lgbm_bull_meta.json").write_text('{"features":["ret_20d"]}', encoding="utf-8")
    monkeypatch.setattr(ml_strategy, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(pickle, "load", lambda _file: DummyModel())

    strategy = ml_strategy.MLStrategy("best")

    assert strategy.is_ready is True
    assert "bull" in strategy._regime_models


def test_ml_strategy_scores_from_pit_feature_store(tmp_path, monkeypatch):
    import backtest.strategies.ml_strategy as ml_strategy

    (tmp_path / "lgbm_best.pkl").write_bytes(b"model")
    (tmp_path / "lgbm_best_meta.json").write_text('{"features":["fund_roe"]}', encoding="utf-8")
    feature_panel = pd.DataFrame(
        {
            "month": ["2026-04"],
            "symbol": ["000001"],
            "fund_roe": [0.2],
            "ret_fwd_20d": [0.0],
        }
    )
    monkeypatch.setattr(ml_strategy, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(pickle, "load", lambda _file: DummyModel())
    monkeypatch.setattr(ml_strategy, "load_feature_panel", lambda hub=None: feature_panel, raising=False)

    strategy = ml_strategy.MLStrategy("best")
    close = pd.Series(
        [10.0] * 90,
        index=pd.date_range("2026-02-01", periods=90, freq="D"),
        name="000001",
    )

    score = strategy.score("000001", close, len(close) - 1, "sideways")

    assert score > 85.0


def test_ml_strategy_prefers_latest_asof_slice_over_prior_month(tmp_path, monkeypatch):
    import backtest.strategies.ml_strategy as ml_strategy

    (tmp_path / "lgbm_best.pkl").write_bytes(b"model")
    (tmp_path / "lgbm_best_meta.json").write_text('{"features":["fund_roe"]}', encoding="utf-8")
    feature_panel = pd.DataFrame(
        {
            "as_of_date": ["2026-04-30", "2026-05-07", "2026-05-10"],
            "month": ["2026-04", "2026-05", "2026-05"],
            "symbol": ["000001", "000001", "000001"],
            "fund_roe": [0.01, 0.30, -0.30],
        }
    )
    monkeypatch.setattr(ml_strategy, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(pickle, "load", lambda _file: DummyModel())
    monkeypatch.setattr(ml_strategy, "load_feature_panel", lambda hub=None: feature_panel, raising=False)

    strategy = ml_strategy.MLStrategy("best")
    prices = pd.Series(
        [10.0] * 90,
        index=pd.date_range("2026-02-08", periods=90, freq="D"),
        name="000001",
    )

    score = strategy.score("000001", prices, len(prices) - 1, "sideways")

    assert score > 95.0


def test_ml_strategy_batches_feature_store_predictions_by_month(tmp_path, monkeypatch):
    import backtest.strategies.ml_strategy as ml_strategy

    model = CountingModel()
    (tmp_path / "lgbm_best.pkl").write_bytes(b"model")
    (tmp_path / "lgbm_best_meta.json").write_text('{"features":["fund_roe"]}', encoding="utf-8")
    feature_panel = pd.DataFrame(
        {
            "month": ["2026-04", "2026-04"],
            "symbol": ["000001", "000002"],
            "fund_roe": [0.2, 0.1],
        }
    )
    monkeypatch.setattr(ml_strategy, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(pickle, "load", lambda _file: model)
    monkeypatch.setattr(ml_strategy, "load_feature_panel", lambda hub=None: feature_panel, raising=False)

    strategy = ml_strategy.MLStrategy("best")
    close = pd.Series([10.0] * 90, index=pd.date_range("2026-02-01", periods=90, freq="D"))

    first = strategy.score("000001", close, len(close) - 1, "sideways")
    second = strategy.score("000002", close, len(close) - 1, "sideways")

    assert first > second > 50
    assert model.calls == 1


def test_ml_backtest_uses_batched_alpha_model():
    from backtest.run_all_strategies import _strategy_alpha_model
    from pipeline.alpha import StrategyAlphaAdapter

    alpha = _strategy_alpha_model("ml_lgbm", "LightGBM ML", lambda *args: 0.0, 30)

    assert alpha.__class__.__name__ == "MLFeatureStoreAlphaModel"
    assert not isinstance(alpha, StrategyAlphaAdapter)


def test_ml_alpha_model_generates_month_signals_with_one_prediction(tmp_path, monkeypatch):
    import backtest.strategies.ml_strategy as ml_strategy

    model = CountingModel()
    (tmp_path / "lgbm_best.pkl").write_bytes(b"model")
    (tmp_path / "lgbm_best_meta.json").write_text('{"features":["fund_roe"]}', encoding="utf-8")
    feature_panel = pd.DataFrame(
        {
            "month": ["2026-04", "2026-04"],
            "symbol": ["000001", "000002"],
            "fund_roe": [0.2, 0.1],
        }
    )
    monkeypatch.setattr(ml_strategy, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(pickle, "load", lambda _file: model)
    monkeypatch.setattr(ml_strategy, "load_feature_panel", lambda hub=None: feature_panel, raising=False)

    alpha = ml_strategy.MLFeatureStoreAlphaModel(min_score=0)
    dates = pd.date_range("2026-02-01", periods=90, freq="D")
    prices = pd.DataFrame({"000001": [10.0] * 90, "000002": [10.0] * 90}, index=dates)

    signals = alpha.generate_alpha(["000001", "000002"], prices, len(prices) - 1, "sideways")

    assert [signal.symbol for signal in signals] == ["000001", "000002"]
    assert signals[0].score > signals[1].score > 50
    assert model.calls == 1


def test_ml_score_map_returns_empty_dict_on_predict_error(tmp_path, monkeypatch):
    import backtest.strategies.ml_strategy as ml_strategy

    (tmp_path / "lgbm_best.pkl").write_bytes(b"model")
    (tmp_path / "lgbm_best_meta.json").write_text('{"features":["fund_roe"]}', encoding="utf-8")
    feature_panel = pd.DataFrame(
        {
            "month": ["2026-04"],
            "symbol": ["000001"],
            "fund_roe": [0.2],
        }
    )
    monkeypatch.setattr(ml_strategy, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(pickle, "load", lambda _file: FailingPredictModel())
    monkeypatch.setattr(ml_strategy, "load_feature_panel", lambda hub=None: feature_panel, raising=False)

    strategy = ml_strategy.MLStrategy("best")
    prices = pd.DataFrame({"000001": [10.0] * 90}, index=pd.date_range("2026-02-01", periods=90, freq="D"))

    score_map = strategy.pit_score_map(prices, len(prices) - 1, "sideways")

    assert score_map == {}
    assert any("predict failed" in err for err in strategy.load_errors)


def test_ml_strategy_coerces_feature_store_objects_to_numeric(tmp_path, monkeypatch):
    import backtest.strategies.ml_strategy as ml_strategy

    (tmp_path / "lgbm_best.pkl").write_bytes(b"model")
    (tmp_path / "lgbm_best_meta.json").write_text('{"features":["val_pe_percentile"]}', encoding="utf-8")
    feature_panel = pd.DataFrame(
        {
            "month": ["2026-04"],
            "symbol": ["000001"],
            "val_pe_percentile": ["0.2"],
        }
    )
    monkeypatch.setattr(ml_strategy, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(pickle, "load", lambda _file: NumericOnlyModel())
    monkeypatch.setattr(ml_strategy, "load_feature_panel", lambda hub=None: feature_panel, raising=False)

    strategy = ml_strategy.MLStrategy("best")
    prices = pd.DataFrame({"000001": [10.0] * 90}, index=pd.date_range("2026-02-01", periods=90, freq="D"))

    score_map = strategy.pit_score_map(prices, len(prices) - 1, "sideways")

    assert score_map["000001"] > 85.0


def test_ml_model_bundle_reports_load_errors(tmp_path, monkeypatch):
    from signals import ml_signals

    (tmp_path / "lgbm_best.pkl").write_bytes(b"broken")
    monkeypatch.setattr(ml_signals, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(ml_signals, "_current_regime", lambda: ("sideways", {"sideways": 1.0}))

    def broken_load(_file):
        raise ModuleNotFoundError("No module named 'lightgbm'")

    monkeypatch.setattr(pickle, "load", broken_load)

    model, features, meta, label = ml_signals._load_model_bundle("best")

    assert model is None
    assert features == []
    assert label == "missing"
    assert any("lightgbm" in err for err in meta["load_errors"])


def test_apply_ranked_buys_never_marks_st_stock_as_buy():
    from signals.selection import apply_ranked_buys

    rows = [
        {"symbol": "000001", "name": "平安银行", "score": 60.0, "signal": "hold"},
        {"symbol": "000056", "name": "*ST皇庭", "score": 99.0, "signal": "hold"},
    ]

    selected = apply_ranked_buys(
        rows,
        "ml_lgbm",
        default_min_score=50,
        default_top_pct=1.0,
        default_min_buys=1,
        default_max_buys=2,
        selection_overrides={"min_score": 50, "top_pct": 1.0, "min_buys": 1, "max_buys": 2},
    )

    by_symbol = {row["symbol"]: row for row in selected}
    assert by_symbol["000056"]["signal"] == "hold"
    assert by_symbol["000056"]["detail"]["tradability_blocked"] is True
    assert by_symbol["000001"]["signal"] == "buy"


def test_paper_execution_uses_configured_fresh_paper_signals_only(tmp_path, monkeypatch):
    import scripts.execute_paper_trades as exec_trades
    from data.storage.datahub import DataHub

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    monkeypatch.setattr(exec_trades, "HUB", hub)
    monkeypatch.setattr(
        exec_trades,
        "load_config",
        lambda: {
            "strategies": {
                "buffett": {"enabled": True, "signal_name": "buffett"},
                "ml_lgbm": {"enabled": True, "signal_name": "ml_lgbm"},
                "trend_following": {"enabled": True, "signal_name": "trend_following"},
            },
            "paper_trading": {
                "strategies": ["buffett", "ml_lgbm"],
                "max_orders_per_strategy": 5,
                "max_signal_age_days": 2,
            },
        },
    )

    hub.write_parquet(
        pd.DataFrame(
            {
                "symbol": ["000001"],
                "signal": ["buy"],
                "score": [70.0],
                "computed_at": [pd.Timestamp.now().isoformat()],
            }
        ),
        hub.signal_path("buffett"),
    )
    hub.write_parquet(
        pd.DataFrame(
            {
                "symbol": ["000002"],
                "signal": ["buy"],
                "score": [99.0],
                "computed_at": ["2000-01-01T00:00:00"],
            }
        ),
        hub.signal_path("ml_lgbm"),
    )
    hub.write_parquet(
        pd.DataFrame(
            {
                "symbol": ["000003"],
                "signal": ["buy"],
                "score": [99.0],
                "computed_at": [pd.Timestamp.now().isoformat()],
            }
        ),
        hub.signal_path("trend_following"),
    )

    signals = exec_trades._read_latest_signals()

    assert signals == {"buffett": [("000001", "buy", 70.0)]}
