import importlib
from pathlib import Path

import pandas as pd
import pytest


def test_data_registry_contract_is_valid():
    from data.data_registry import get_registry

    reg = get_registry()
    assert reg.validate() == []
    meta = reg.health_metadata(repairable_tables={"stock_daily"})
    assert meta["stock_daily"].registry_key == "ohlcv_daily"
    assert meta["stock_daily"].freshness_sla_days == 5
    assert meta["stock_daily"].partition_key == "symbol"
    assert meta["stock_daily"].repairable is True


def test_datahub_expands_registry_dimension_paths(tmp_path):
    from data.datahub import DataHub

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
    from data.datahub import DataHub

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


def test_db_health_scans_moneyflow_symbol_and_tushare_daily(tmp_path, monkeypatch):
    from data.datahub import DataHub, reset_datahub

    store = tmp_path / "store"
    cache = tmp_path / "cache"
    monkeypatch.setenv("QUANT_AGENT_STORE", str(store))
    monkeypatch.setenv("QUANT_AGENT_CACHE", str(cache))
    reset_datahub()

    hub = DataHub(store_root=store, cache_root=cache)
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


def test_daily_cron_ohlcv_uses_stock_daily_module(monkeypatch):
    import scripts.cron_fetch_daily as daily
    import data.fetchers.stock_daily as stock_daily

    monkeypatch.setattr(daily, "_load_pool", lambda pool_size=0: ["000001", "000002"])
    monkeypatch.setattr(
        stock_daily,
        "fetch_all",
        lambda symbols: {sym: pd.DataFrame({"date": ["2026-05-20"], "close": [1.0]}) for sym in symbols},
    )

    assert daily.fetch_ohlcv(pool_size=2) == 2


def test_financials_uses_canonical_symbol_path(tmp_path):
    from data.datahub import DataHub

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    expected = tmp_path / "store" / "stock" / "financials" / "000001.parquet"

    assert hub.stock_financial_path("000001") == expected
