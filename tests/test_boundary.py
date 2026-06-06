import numpy as np
import pandas as pd
import pytest


def _compute_series(factor, df: pd.DataFrame) -> pd.Series:
    return pd.Series([factor.compute(df, i) for i in range(len(df))], index=df.index)


def test_factor_expression_boundary_handles_formula_and_missing_inputs():
    from signals.dsl_parser import compute_formula
    from signals.expression import Delta, MA, Ret, Std

    df = pd.DataFrame(
        {
            "close": [10, 12, 11, 13, 14, 12, 15, 16, 14, 17],
            "roe": [0.08, 0.10, 0.12, 0.14, 0.15, 0.16, 0.18, 0.19, 0.20, 0.22],
            "pe": [30, 28, 25, 22, 20, 21, 18, 17, 19, 15],
        },
        index=pd.date_range("2024-01-01", periods=10, freq="B"),
    )

    close = Ret("close")
    momentum = _compute_series(Delta(close, 3) / close, df)
    ma5 = _compute_series(MA(close, 5), df)
    volatility = _compute_series(Std(Delta(close, 1), 5), df)
    parsed = compute_formula("Delta(close,3)/close_t", df, len(df) - 1)
    lagged_ref = compute_formula("close_t / close_t-3 - 1", df, 5)

    assert momentum.dropna().abs().sum() > 0
    assert ma5.dropna().sum() > 0
    assert volatility.dropna().mean() > 0
    assert not pd.isna(parsed)
    assert lagged_ref == pytest.approx(12 / 11 - 1)

    empty = _compute_series(Ret("close"), pd.DataFrame({"close": []}))
    assert empty.empty
    assert pd.isna(Ret("nonexistent").compute(df, 0))

    df_nan = pd.DataFrame({"close": [10, np.nan, 12]})
    result_nan = _compute_series(Delta(Ret("close"), 1), df_nan)
    assert len(result_nan) == 3


def test_risk_analytics_boundary_handles_normal_and_degenerate_returns():
    from backtest.analytics import RiskAnalytics

    returns = pd.Series(
        [
            0.01,
            -0.02,
            0.03,
            -0.01,
            0.02,
            -0.03,
            0.01,
            0.02,
            -0.01,
            0.04,
            -0.02,
            0.01,
            0.03,
            -0.01,
            0.02,
            0.01,
            -0.02,
            0.03,
            -0.01,
            0.02,
        ],
        index=pd.date_range("2024-01-01", periods=20, freq="B"),
    )
    benchmark = pd.Series(
        [
            0.005,
            -0.01,
            0.02,
            0.0,
            0.01,
            -0.02,
            0.01,
            0.01,
            -0.005,
            0.02,
            -0.01,
            0.0,
            0.02,
            0.0,
            0.01,
            0.005,
            -0.01,
            0.02,
            0.0,
            0.01,
        ],
        index=pd.date_range("2024-01-01", periods=20, freq="B"),
    )

    risk_free = pd.Series([0.015] * len(returns), index=returns.index)
    metrics = RiskAnalytics.compute(returns, benchmark, risk_free_rates=risk_free)
    assert metrics.sharpe > 0
    assert metrics.max_drawdown < 0
    assert 0 <= metrics.win_rate <= 1
    assert abs(metrics.beta) > 0
    assert abs(metrics.alpha) < 100

    positive_index = pd.date_range("2024-02-01", periods=20, freq="B")
    positive_returns = pd.Series([0.01] * 20, index=positive_index)
    positive_rf = pd.Series([0.015] * len(positive_returns), index=positive_returns.index)
    all_positive = RiskAnalytics.compute(positive_returns, risk_free_rates=positive_rf)
    assert all_positive.win_rate == 1.0
    assert all_positive.max_drawdown == 0.0

    single = RiskAnalytics.compute(pd.Series([0.01]))
    assert single.sharpe == 0.0


def test_paper_broker_boundary_enforces_t_plus_one_and_affordability():
    from broker import PaperBroker

    broker = PaperBroker(initial_cash=100_000)
    broker.set_prices({"000001": 12.50, "600519": 1500.00})

    first_order = broker.submit_order("000001", price=12.50, volume=100, side="buy")
    second_order = broker.submit_order("600519", price=1500.00, volume=10, side="buy")

    assert first_order.startswith("PAPER_")
    assert second_order.startswith("PAPER_")
    assert len(broker.get_positions()) == 2
    assert abs(broker.get_balance().total_asset - 100_000) < 20

    assert broker.submit_order("000001", price=13.00, volume=50, side="sell").startswith("T+1")
    assert broker.submit_order("600519", price=1510.00, volume=10, side="sell").startswith("T+1")

    broker.end_of_day()
    sell_order = broker.submit_order("000001", price=13.00, volume=50, side="sell")
    position = next((p for p in broker.get_positions() if p.code == "000001"), None)

    assert sell_order.startswith("PAPER_")
    assert position is not None
    assert position.volume == 50

    small_account = PaperBroker(initial_cash=1_000, enable_risk=False)
    overbuy_order = small_account.submit_order("000001", price=100.00, volume=100, side="buy")
    assert overbuy_order.startswith("PAPER_") or overbuy_order == "资金不足"


def test_datahub_duckdb_and_results_store_boundary_are_isolated(tmp_path, monkeypatch):
    from data.storage.datahub import DataHub
    import data.storage.db as db_module
    from data import results_db

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    monkeypatch.setattr(db_module, "_HUB", hub)
    monkeypatch.setattr(db_module, "_STORE_DIR", hub.store_dir())
    monkeypatch.setattr(results_db, "HUB", hub)
    monkeypatch.setattr(results_db, "STORE", hub.store_dir())
    monkeypatch.setattr(results_db, "SIGNALS_DIR", hub.signals_dir())
    db_module.reset_db()

    signal_path = hub.signal_path("unit_strategy")
    hub.write_parquet(
        pd.DataFrame(
            [
                {"symbol": "A", "signal": "hold", "computed_at": "2026-05-01T15:00:00"},
                {"symbol": "B", "signal": "buy", "computed_at": "2026-05-02T15:00:00"},
                {"symbol": "C", "signal": "buy", "computed_at": "2026-05-02T15:00:00"},
            ]
        ),
        signal_path,
    )

    latest = hub.latest_batch(signal_path)
    assert sorted(latest["symbol"].tolist()) == ["B", "C"]

    hub.append_parquet(
        signal_path,
        {"symbol": "B", "signal": "sell", "computed_at": "2026-05-03T15:00:00"},
        dedupe_subset=["symbol"],
    )
    row_b = hub.read_parquet(signal_path).query("symbol == 'B'").iloc[0].to_dict()
    assert row_b["signal"] == "sell"

    audit_keys = {item["key"] for item in hub.audit()}
    assert {"signals", "features", "paper", "token_usage"}.issubset(audit_keys)

    db = db_module.get_db()
    db.execute("CREATE TABLE IF NOT EXISTS _test (id INT, name TEXT)")
    db.execute("INSERT INTO _test VALUES (1, 'test')")
    row = db.fetchone("SELECT * FROM _test WHERE id=1")
    assert row["name"] == "test"
    db.execute("DROP TABLE _test")

    results_db.init()
    results_db.save_buffett_results(
        [
            {
                "symbol": "TEST01",
                "name": "测试股",
                "industry": "银行",
                "sector": "bank",
                "verdict": "通过-护城河",
                "score": 85.0,
                "roe": 15.5,
                "gross_margin": 0,
                "net_margin": 12.3,
                "de": 6.5,
                "safety_margin": 35.2,
                "dcf_value": 100.0,
                "current_price": 65.0,
            }
        ]
    )
    meta = results_db.get_buffett_meta()
    assert meta["total"] == 1
    assert meta["passed"] == 1

    db_module.reset_db()


def test_signal_selection_boundary_uses_full_lookback_and_global_gates(tmp_path, monkeypatch):
    from signals.multifactor import compute_momentum
    from signals.selection import apply_ranked_buys

    settings = tmp_path / "settings.yaml"
    settings.write_text("signal_selection: {}\n", encoding="utf-8")
    monkeypatch.setenv("ASTROLABE_SETTINGS", str(settings))

    price_df = pd.DataFrame({"close": [float(i) for i in range(1, 81)]})
    momentum = compute_momentum(price_df, [21])
    momentum_skip = compute_momentum(price_df, [42], skip_recent=21)

    assert momentum[21] == pytest.approx(80 / 59 - 1)
    assert momentum_skip[42] == pytest.approx(59 / 17 - 1)

    ranked = apply_ranked_buys(
        [{"symbol": f"S{i}", "score": score, "signal": "hold"} for i, score in enumerate([40, 80, 70, 60, 55])],
        "unit_test",
        default_min_score=60,
        default_top_pct=0.4,
        default_min_buys=1,
        default_max_buys=2,
    )
    buy_symbols = [row["symbol"] for row in ranked if row["signal"] == "buy"]

    assert [row["symbol"] for row in ranked[:3]] == ["S1", "S2", "S3"]
    assert buy_symbols == ["S1", "S2", "S3", "S4"]
    assert ranked[0]["detail"]["selection_min_score"] == 50.0
