import importlib
from pathlib import Path

import pandas as pd
import pytest


def test_data_registry_contract_is_valid():
    from data.storage.dimensions import get_registry

    reg = get_registry()
    assert reg.validate() == []
    meta = reg.health_metadata(repairable_tables={"stock_daily"})
    assert meta["stock_daily"].registry_key == "ohlcv_daily"
    assert meta["stock_daily"].freshness_sla_days == 5
    assert meta["stock_daily"].partition_key == "symbol"
    assert meta["stock_daily"].repairable is True


def test_datahub_expands_registry_dimension_paths(tmp_path):
    from data.storage.datahub import DataHub

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")

    assert hub.dimension_root("ohlcv_daily") == tmp_path / "store" / "stock" / "daily"
    assert hub.dimension_path("ohlcv_daily", symbol="000001") == tmp_path / "store" / "stock" / "daily" / "000001.parquet"
    assert hub.dimension_path("moneyflow_tushare_daily", YYYYMMDD="20260520") == (
        tmp_path / "store" / "stock" / "moneyflow" / "daily" / "20260520.parquet"
    )

    with pytest.raises(KeyError):
        hub.dimension_path("ohlcv_daily")
    with pytest.raises(ValueError):
        hub.dimension_path("ohlcv_daily", symbol="../escape")


def test_datahub_writes_manifest_for_parquet(tmp_path):
    from data.storage.datahub import DataHub

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    path = hub.dimension_path("ohlcv_daily", symbol="000001")
    hub.write_parquet(pd.DataFrame({"date": ["2026-05-20"], "close": [1.0]}), path, producer="unit-test")

    manifest = hub.manifest_for(path)
    assert manifest["producer"] == "unit-test"
    assert manifest["row_count"] == 1
    assert manifest["date_min"] == "2026-05-20"
    assert manifest["date_max"] == "2026-05-20"
    assert manifest["schema_hash"]
    assert manifest["file_sha256"]


def test_datahub_facade_delegates_to_internal_components(tmp_path):
    from data.storage.datahub import DataHub
    from data.storage.datahub_dimensions import DimensionStore
    from data.storage.datahub_manifest import ManifestStore
    from data.storage.datahub_parquet import ParquetStore
    from data.storage.datahub_paths import DataHubPaths

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")

    assert isinstance(hub.paths, DataHubPaths)
    assert isinstance(hub.parquet, ParquetStore)
    assert isinstance(hub.manifest, ManifestStore)
    assert isinstance(hub.dimensions, DimensionStore)

    assert hub.signal_path("unit_strategy") == hub.paths.signal_path("unit_strategy")
    assert hub.dimension_path("ohlcv_daily", symbol="000001") == (
        tmp_path / "store" / "stock" / "daily" / "000001.parquet"
    )

    target = hub.signal_path("unit_strategy")
    hub.write_parquet(pd.DataFrame({"date": ["2026-05-20"], "signal": ["buy"]}), target, producer="facade-test")

    assert hub.read_parquet(target)["signal"].tolist() == ["buy"]
    assert hub.manifest_for(target)["producer"] == "facade-test"


def test_db_health_scans_moneyflow_symbol_and_tushare_daily(tmp_path, monkeypatch):
    from data.storage.datahub import get_datahub, reset_datahub

    runtime = tmp_path / "runtime"
    store = runtime / "store"
    monkeypatch.setenv("ASTROLABE_VAR", str(runtime))
    reset_datahub()

    hub = get_datahub()
    hub.write_parquet(
        pd.DataFrame({"日期": ["2026-05-20"], "主力净流入-净额": [100.0]}),
        hub.dimension_path("moneyflow_daily", symbol="000001"),
    )
    hub.write_parquet(
        pd.DataFrame({"trade_date": ["20260520"], "ts_code": ["000001.SZ"], "net_mf_amount": [100.0]}),
        hub.dimension_path("moneyflow_tushare_daily", YYYYMMDD="20260520"),
    )

    import scripts.db_health_check as health

    health = importlib.reload(health)
    result = health.run_health_check(output_path=store / "db_health.parquet")

    tables = set(result["table"])

    daily = result[result["table"] == "stock_moneyflow_daily"].iloc[0].to_dict()
    tushare_daily = result[result["table"] == "stock_moneyflow_tushare_daily"].iloc[0].to_dict()

    assert "stock_moneyflow_daily" in tables
    assert "stock_moneyflow_tushare_daily" in tables
    assert daily["registry_key"] == "moneyflow_daily"
    assert tushare_daily["partition_key"] == "trade_date"
    assert daily["freshness_status"] in {"fresh", "stale"}
    assert int(daily["manifest_files"]) == 1
    reset_datahub()


def test_db_health_prefers_explicit_date_over_quarter_column():
    import scripts.db_health_check as health

    frame = pd.DataFrame(
        {
            "quarter": ["2025Q4"],
            "date": [pd.Timestamp("2025-12-31")],
            "gdp": [1401879.2],
        }
    )

    assert health._find_date_col(frame) == "date"
    assert health._freshness_days(frame) == (
        pd.Timestamp.today().date() - pd.Timestamp("2025-12-31").date()
    ).days


def test_datahub_uses_canonical_runtime_env(tmp_path, monkeypatch):
    from data.storage.datahub import DataHub

    runtime = tmp_path / "astrolabe-runtime"
    monkeypatch.setenv("ASTROLABE_VAR", str(runtime))

    hub = DataHub(create=False)

    assert hub.store_root == (runtime / "store").resolve()
    assert hub.cache_root == (runtime / "cache").resolve()


def test_default_datahub_rebuilds_when_runtime_env_changes(tmp_path, monkeypatch):
    from data.storage.datahub import get_datahub, reset_datahub

    first_runtime = tmp_path / "first-runtime"
    second_runtime = tmp_path / "second-runtime"

    monkeypatch.setenv("ASTROLABE_VAR", str(first_runtime))
    reset_datahub()
    first = get_datahub()
    assert first.store_root == (first_runtime / "store").resolve()

    monkeypatch.setenv("ASTROLABE_VAR", str(second_runtime))
    second = get_datahub()

    assert second.store_root == (second_runtime / "store").resolve()
    assert second.cache_root == (second_runtime / "cache").resolve()
    reset_datahub()


def test_daily_cron_ohlcv_uses_stock_daily_module(monkeypatch):
    import scripts.cron_fetch_daily as daily
    import data.ingestion.fetchers.stock_daily as stock_daily

    monkeypatch.setattr(daily, "_load_pool", lambda pool_size=0: ["000001", "000002"])
    monkeypatch.setattr(
        stock_daily,
        "fetch_all",
        lambda symbols: {sym: pd.DataFrame({"date": ["2026-05-20"], "close": [1.0]}) for sym in symbols},
    )

    assert daily.fetch_ohlcv(pool_size=2) == 2


def test_financials_uses_canonical_symbol_path(tmp_path):
    from data.storage.datahub import DataHub

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    expected = tmp_path / "store" / "stock" / "financials" / "000001.parquet"

    assert hub.stock_financial_path("000001") == expected
