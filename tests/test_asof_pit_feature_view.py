from __future__ import annotations

import pandas as pd
import numpy as np


def test_feature_store_selects_latest_slice_on_or_before_as_of(tmp_path):
    from data.features.feature_store import latest_feature_file, write_feature_slice

    write_feature_slice(
        pd.DataFrame({"symbol": ["000001"], "as_of_date": ["2026-05-07"], "daily_close": [10.0]}),
        "2026-05-07",
        directory=tmp_path,
    )
    write_feature_slice(
        pd.DataFrame({"symbol": ["000001"], "as_of_date": ["2026-05-10"], "daily_close": [11.0]}),
        "2026-05-10",
        directory=tmp_path,
    )

    selected = latest_feature_file(tmp_path, as_of="2026-05-08")

    assert selected is not None
    assert selected.name == "2026-05-07.parquet"


def test_feature_store_ignores_month_keyed_feature_slices(tmp_path):
    from data.features.feature_store import load_feature_panel

    pd.DataFrame({"symbol": ["000001"], "month": ["2026-04"], "daily_close": [9.0]}).to_parquet(
        tmp_path / "2026-04.parquet",
        index=False,
    )

    try:
        load_feature_panel(directory=tmp_path)
    except RuntimeError as exc:
        assert "No features found" in str(exc)
    else:
        raise AssertionError("month-keyed feature slices must not be loaded")


def test_build_asof_uses_exact_daily_price_not_month_end(tmp_path, monkeypatch):
    import scripts.build_features as build_features

    monkeypatch.setattr(build_features, "FEATURES_DIR", tmp_path)
    monkeypatch.setattr(build_features.HUB, "features_dir", lambda: tmp_path)
    monkeypatch.setattr(build_features.HUB, "feature_path", lambda key: tmp_path / f"{key}.parquet")
    monkeypatch.setattr("data.features.feature_store.HUB", build_features.HUB)

    prices = pd.DataFrame(
        {
            "close": [8.0, 10.0, 12.0],
            "open": [8.0, 10.0, 12.0],
            "high": [8.0, 10.0, 12.0],
            "low": [8.0, 10.0, 12.0],
            "volume": [100, 100, 100],
        },
        index=pd.to_datetime(["2026-05-06", "2026-05-08", "2026-05-29"]),
    )

    rows = build_features._build_asof(
        "2026-05-08",
        {"000001": prices},
        {"000001": pd.DataFrame({"daily_close": prices["close"]}, index=prices.index)},
        {},
        {},
        force=True,
        min_bars=1,
    )
    saved = pd.read_parquet(tmp_path / "2026-05-08.parquet")

    assert rows == 1
    assert saved.loc[0, "as_of_date"] == "2026-05-08"
    assert saved.loc[0, "month"] == "2026-05"
    assert saved.loc[0, "daily_close"] == 10.0


def test_vectorized_alpha_features_match_expression_dsl():
    import scripts.build_features as build_features
    from signals.expression import alpha_factors

    dates = pd.date_range("2026-01-01", periods=90, freq="B")
    base = np.linspace(10.0, 18.0, len(dates))
    prices = pd.DataFrame(
        {
            "open": base + np.sin(np.arange(len(dates))) * 0.1,
            "high": base + 0.6,
            "low": base - 0.5,
            "close": base + np.cos(np.arange(len(dates))) * 0.1,
            "volume": np.linspace(1000.0, 3000.0, len(dates)),
        },
        index=dates,
    )

    vectorized = build_features._compute_technical_factor_frame(prices)
    factors = alpha_factors()
    idx = 75
    for name, factor in factors.items():
        expected = factor.compute(prices, idx)
        actual = vectorized.iloc[idx][name]
        if pd.isna(expected):
            assert pd.isna(actual), name
        else:
            assert np.isclose(actual, expected, rtol=1e-10, atol=1e-10), name


def test_time_series_splitter_accepts_asof_dates():
    from data.features.feature_store import feature_time_key_column, feature_period_key

    df = pd.DataFrame(
        {
            "symbol": ["000001", "000001", "000001"],
            "as_of_date": ["2026-01-03", "2026-01-10", "2026-02-03"],
            "month": ["2026-01", "2026-01", "2026-02"],
        }
    )

    assert feature_time_key_column(df) == "as_of_date"
    assert feature_period_key(df["as_of_date"]).tolist() == ["2026-01", "2026-01", "2026-02"]
