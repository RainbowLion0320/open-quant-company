import pandas as pd


def test_dotted_settings_helpers_read_write_nested_mappings_without_flat_keys():
    from core.settings import get_dotted, set_dotted

    data = {"ingestion": {"fetcher": {"min_interval": 3.0}}}

    assert get_dotted(data, "ingestion.fetcher.min_interval") == 3.0
    assert get_dotted(data, "ingestion.fetcher.max_retries", default=3) == 3
    assert get_dotted({"ingestion.fetcher": {"bad": True}}, "ingestion.fetcher") is None

    set_dotted(data, "ingestion.fetcher.max_retries", 4)
    set_dotted(data, "signals.multifactor.weights.quality", 0.35)

    assert data["ingestion"]["fetcher"]["max_retries"] == 4
    assert data["signals"]["multifactor"]["weights"]["quality"] == 0.35
    assert "ingestion.fetcher" not in data


def test_settings_loader_supports_project_root_env_and_dotted_sections(tmp_path, monkeypatch):
    root = tmp_path / "project"
    cfg_dir = root / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "settings.yaml").write_text(
        """
project:
  name: test-project
data:
  tushare:
    token: file-token
signals:
  multifactor:
    buy_threshold: 60
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("ASTROLABE_HOME", str(root))
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_PRO_TOKEN", raising=False)

    from core.settings import get_section, get_settings, get_tushare_token, resolve_settings_path

    assert resolve_settings_path() == cfg_dir / "settings.yaml"
    assert get_settings(refresh=True)["project"]["name"] == "test-project"
    assert get_section("signals.multifactor") == {"buy_threshold": 60}
    assert get_tushare_token() == ""

    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    assert get_tushare_token() == "env-token"


def test_symbol_helpers_normalize_a_share_codes_and_exchange_formats():
    from data.market.symbols import normalize_symbol, to_sina_symbol, to_ts_code

    assert normalize_symbol("SH600519") == "600519"
    assert normalize_symbol("000001.SZ") == "000001"
    assert normalize_symbol("688001") == "688001"
    assert to_sina_symbol("600519.SH") == "sh600519"
    assert to_sina_symbol("000001") == "sz000001"
    assert to_ts_code("600519") == "600519.SH"
    assert to_ts_code("000001") == "000001.SZ"
    assert to_ts_code("920001") == "920001.BJ"


def test_fetcher_base_rate_limiter_uses_configurable_jitter(monkeypatch):
    calls: list[float] = []

    monkeypatch.setattr("data.ingestion.fetchers.base.time.sleep", lambda seconds: calls.append(seconds))
    monkeypatch.setattr("data.ingestion.fetchers.base.random.uniform", lambda low, high: 0.25)

    from data.ingestion.fetchers.base import RateLimiter

    RateLimiter(base_seconds=1.0, jitter_seconds=0.5).sleep()
    assert calls == [1.25]


def test_api_serializer_converts_nan_and_time_series_consistently():
    import numpy as np

    from web.api.serializers import date_value_series, json_value, safe_float, safe_int

    assert safe_float(float("nan"), default=-1.0) == -1.0
    assert safe_int(None, default=7) == 7
    assert json_value(np.float64(1.25)) == 1.25

    df = pd.DataFrame(
        {
            "date": ["2026-05-20", "bad-date", "2026-05-21"],
            "close": [1.23456, 999.0, 2.34567],
        }
    )
    assert date_value_series(df, "close", limit=5) == [
        {"date": "2026-05-20", "value": 1.2346},
        {"date": "2026-05-21", "value": 2.3457},
    ]


def test_datahub_latest_dimension_snapshot_uses_registry_path_only(tmp_path):
    from data.storage.datahub import DataHub

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    registry_root = hub.dimension_root("sector_performance_snapshot")
    registry_root.mkdir()
    old = registry_root / "2026-05-20.parquet"
    new = registry_root / "2026-05-22.parquet"
    for path in [old, new]:
        path.touch()

    assert hub.latest_dimension_snapshot("sector_performance_snapshot") == new

    for path in [old, new]:
        path.unlink()
    assert hub.latest_dimension_snapshot("sector_performance_snapshot") is None

    membership = hub.dimension_root("sector_membership")
    membership.parent.mkdir(parents=True, exist_ok=True)
    membership.touch()
    assert hub.latest_dimension_snapshot("sector_membership") == membership


def test_datahub_lists_dimension_snapshots_for_file_and_partitioned_dimensions(tmp_path):
    from data.storage.datahub import DataHub

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    root = hub.dimension_root("sector_signal_snapshot")
    root.mkdir(parents=True)
    old = root / "2026-05-20.parquet"
    new = root / "2026-05-22.parquet"
    ignored = root / "notes.txt"
    for path in [new, old, ignored]:
        path.touch()

    assert hub.list_dimension_snapshots("sector_signal_snapshot") == [old, new]

    membership = hub.dimension_root("sector_membership")
    membership.parent.mkdir(parents=True, exist_ok=True)
    membership.touch()
    assert hub.list_dimension_snapshots("sector_membership") == [membership]


def test_feature_store_loads_feature_files_panel_and_latest_frame(tmp_path, monkeypatch):
    from data.features import feature_store
    from data.storage.datahub import DataHub

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    feature_dir = hub.features_dir()
    feature_dir.mkdir(parents=True, exist_ok=True)
    hub.write_parquet(pd.DataFrame({"symbol": ["A"], "factor": [1.0]}), feature_dir / "2026-04-30.parquet")
    hub.write_parquet(
        pd.DataFrame({"symbol": ["B"], "factor": [2.0], "month": ["manual"]}),
        feature_dir / "2026-05-07.parquet",
    )
    hub.write_parquet(pd.DataFrame({"symbol": ["META"]}), feature_dir / "scan_meta.parquet")

    monkeypatch.setattr(feature_store, "HUB", hub)
    monkeypatch.setattr(feature_store, "FEATURES_DIR", feature_dir)

    files = feature_store.iter_feature_files()
    panel = feature_store.load_feature_panel()
    latest = feature_store.latest_feature_frame()

    assert [path.name for path in files] == ["2026-04-30.parquet", "2026-05-07.parquet"]
    assert panel[["symbol", "month"]].to_dict(orient="records") == [
        {"symbol": "A", "month": "2026-04"},
        {"symbol": "B", "month": "manual"},
    ]
    assert latest["symbol"].tolist() == ["B"]


def test_buffett_score_estimator_is_shared_and_bounded():
    from signals.scoring import estimate_buffett_score

    assert estimate_buffett_score({"roe_history": [0.12, 0.14, 0.16]}) == 70.0
    assert estimate_buffett_score({"roe_history": [0.5, 0.6, 0.7, 0.8, 0.9]}) == 100.0
    assert estimate_buffett_score({"roe_history": []}) == 0.0


def test_technical_factor_helpers_are_point_in_time_and_shared():
    from signals.technical import momentum_score, technical_factors_from_series

    dates = pd.date_range("2026-01-01", periods=140, freq="D")
    close = pd.Series(range(100, 240), index=dates, dtype="float64")

    factors = technical_factors_from_series(close, 126)

    assert factors["momentum_1m"] > 0
    assert factors["momentum_3m_skip_1m"] > 0
    assert factors["momentum_6m_skip_1m"] > 0
    assert factors["volatility"] >= 0
    assert momentum_score(close, dates[126]) > 0


def test_cybernetic_scoring_uses_shared_regime_sector_preferences():
    from signals.scoring import score_cybernetic_from_factors

    tech = {
        "trend_strength": 0.05,
        "momentum_3m_skip_1m": 0.08,
        "volatility": 0.20,
    }

    favored = score_cybernetic_from_factors("电子", "bull", tech)
    unfavored = score_cybernetic_from_factors("银行", "bull", tech)
    defensive_bear = score_cybernetic_from_factors("银行", "bear", tech)
    cyclical_bear = score_cybernetic_from_factors("电子", "bear", tech)

    assert favored > unfavored
    assert defensive_bear > cyclical_bear


def test_monthly_momentum_runner_uses_shared_selection_and_execution_helpers():
    from backtest.momentum import run_monthly_rebalance_strategy, select_top_momentum

    class ZeroCostExchange:
        @staticmethod
        def calc_cost(price, shares, side):
            return 0.0

    dates = pd.date_range("2025-01-01", periods=130, freq="D")
    prices = pd.DataFrame(
        {
            "UP": [10 + i * 0.2 for i in range(len(dates))],
            "FLAT": [10.0 for _ in dates],
        },
        index=dates,
    )

    selected = select_top_momentum(prices, dates[-1], 1)
    result, trades = run_monthly_rebalance_strategy(
        prices,
        dates,
        ZeroCostExchange(),
        n_pos=1,
        cash=100_000,
    )

    assert selected[0][0] == "UP"
    assert trades > 0
    assert result > 0
