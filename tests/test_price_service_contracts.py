import os
from pathlib import Path

import pandas as pd
import pytest


def test_price_mode_metadata_round_trips_on_dataframe():
    from data.market.price_types import PriceFrameMetadata, PriceMode, attach_price_metadata, price_metadata

    frame = pd.DataFrame({"date": ["2026-01-02"], "close": [10.0]})
    attach_price_metadata(
        frame,
        PriceFrameMetadata(
            requested_mode=PriceMode.QFQ,
            actual_mode=PriceMode.QFQ,
            source="unit",
            adjustment_source="adj_factor",
        ),
    )

    meta = price_metadata(frame)
    assert meta.requested_mode == PriceMode.QFQ
    assert meta.actual_mode == PriceMode.QFQ
    assert meta.adjusted is True
    assert meta.source == "unit"
    assert frame.attrs["price_mode"] == "qfq"


def test_invalid_price_mode_is_rejected():
    from data.market.price_types import normalize_price_mode

    with pytest.raises(ValueError):
        normalize_price_mode("split_adjusted")


def test_ohlcv_contract_declares_price_mode():
    from data.quality.contract import derive_contracts_from_registry

    contract = derive_contracts_from_registry()["ohlcv_daily"]

    assert contract.price_mode == "qfq"
    assert contract.adjustment_source == "provider_adjusted"


def test_datahub_manifest_records_price_metadata(tmp_path):
    from data.storage.datahub import DataHub
    from data.market.price_types import PriceFrameMetadata, PriceMode, attach_price_metadata

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    frame = pd.DataFrame({"date": ["2026-01-02"], "close": [10.0]})
    attach_price_metadata(
        frame,
        PriceFrameMetadata(
            requested_mode=PriceMode.RAW,
            actual_mode=PriceMode.RAW,
            source="unit",
            adjustment_source="raw",
        ),
    )

    path = hub.stock_daily_raw_path("000001")
    hub.write_parquet(frame, path, producer="unit")

    manifest = hub.manifest_for(path)
    assert manifest["price_mode"] == "raw"
    assert manifest["requested_price_mode"] == "raw"
    assert manifest["price_adjustment_source"] == "raw"


def test_stock_daily_cache_path_respects_adjust_mode(tmp_path, monkeypatch):
    from data.storage.datahub import DataHub
    import data.ingestion.fetchers.stock_daily as stock_daily

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    monkeypatch.setattr(stock_daily, "HUB", hub)
    hub.write_parquet(pd.DataFrame({"date": ["2026-01-02"], "close": [10.0]}), hub.stock_daily_raw_path("000001"))
    hub.write_parquet(pd.DataFrame({"date": ["2026-01-02"], "close": [9.0]}), hub.stock_daily_path("000001"))

    raw = stock_daily.read_one("000001", adjust="raw")
    qfq = stock_daily.read_one("000001", adjust="qfq")

    assert raw["close"].tolist() == [10.0]
    assert qfq["close"].tolist() == [9.0]


def test_adjust_ohlcv_derives_qfq_and_hfq_from_raw_and_adj_factor():
    from data.market.price_service import adjust_ohlcv

    raw = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02"],
            "open": [10.0, 20.0],
            "high": [11.0, 22.0],
            "low": [9.0, 18.0],
            "close": [10.0, 20.0],
            "volume": [100.0, 200.0],
        }
    )
    adj = pd.DataFrame(
        {
            "trade_date": ["20260101", "20260102"],
            "adj_factor": [1.0, 2.0],
        }
    )

    qfq = adjust_ohlcv(raw, adj, mode="qfq")
    hfq = adjust_ohlcv(raw, adj, mode="hfq")

    assert qfq["close"].round(4).tolist() == [5.0, 20.0]
    assert qfq["open"].round(4).tolist() == [5.0, 20.0]
    assert qfq["volume"].tolist() == [100.0, 200.0]
    assert hfq["close"].round(4).tolist() == [10.0, 40.0]


def test_price_service_derives_qfq_from_raw_store(tmp_path):
    from data.storage.datahub import DataHub
    from data.market.price_service import get_stock_prices
    from data.market.price_types import PriceMode, price_metadata

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    hub.write_parquet(
        pd.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02"],
                "open": [10.0, 20.0],
                "high": [11.0, 22.0],
                "low": [9.0, 18.0],
                "close": [10.0, 20.0],
                "volume": [100.0, 200.0],
            }
        ),
        hub.stock_daily_raw_path("000001"),
    )
    hub.write_parquet(
        pd.DataFrame({"trade_date": ["20260101", "20260102"], "adj_factor": [1.0, 2.0]}),
        hub.stock_adj_factor_path("000001"),
    )

    prices = get_stock_prices("000001", mode="qfq", hub=hub)

    assert prices["close"].round(4).tolist() == [5.0, 20.0]
    assert price_metadata(prices).requested_mode == PriceMode.QFQ
    assert price_metadata(prices).actual_mode == PriceMode.QFQ
    assert price_metadata(prices).adjustment_source == "adj_factor"


def test_price_matrix_cache_key_includes_symbol_list(tmp_path):
    from data.storage.datahub import DataHub
    from data.market.price_service import get_stock_price_matrix

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    for symbol, close in (("000001", 10.0), ("000002", 20.0)):
        hub.write_parquet(
            pd.DataFrame(
                {
                    "date": ["2026-01-01"],
                    "open": [close],
                    "high": [close],
                    "low": [close],
                    "close": [close],
                    "volume": [100.0],
                }
            ),
            hub.stock_daily_raw_path(symbol),
        )
        hub.write_parquet(
            pd.DataFrame({"trade_date": ["20260101"], "adj_factor": [1.0]}),
            hub.stock_adj_factor_path(symbol),
        )
        for path in (hub.stock_daily_raw_path(symbol), hub.stock_adj_factor_path(symbol)):
            os.utime(path, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))

    first, _ = get_stock_price_matrix(["000001"], hub=hub, cache_dir=tmp_path / "matrix_cache", min_bars=1)
    second, _ = get_stock_price_matrix(["000002"], hub=hub, cache_dir=tmp_path / "matrix_cache", min_bars=1)

    assert first.columns.tolist() == ["000001"]
    assert second.columns.tolist() == ["000002"]


def test_price_service_use_case_modes_are_explicit():
    from data.market.price_service import price_mode_for_use_case

    assert price_mode_for_use_case("backtest") == "qfq"
    assert price_mode_for_use_case("research") == "qfq"
    assert price_mode_for_use_case("execution") == "raw"
    assert price_mode_for_use_case("valuation") == "raw"


def test_major_price_consumers_declare_price_use_cases():
    expectations = {
        "backtest/run_all_strategies.py": ("get_stock_price_matrix", "PriceUseCase.BACKTEST"),
        "scripts/build_features.py": ("get_stock_prices", "PriceUseCase.RESEARCH"),
        "signals/candidates/common.py": ("get_stock_prices", "PriceUseCase.SIGNAL"),
        "signals/runners.py": ("get_latest_price", "PriceUseCase.VALUATION"),
        "signals/ml_signals.py": ("get_stock_prices", "PriceUseCase.SIGNAL"),
        "scripts/execute_paper_trades.py": ("get_stock_prices", "PriceUseCase.EXECUTION"),
        "web/api/services/dcf.py": ("get_stock_prices", "PriceUseCase.VALUATION"),
        "web/api/routes/portfolio.py": ("get_stock_prices", "PriceUseCase.EXECUTION"),
        "web/api/services/stocks.py": ("get_stock_prices", "PriceUseCase.DISPLAY"),
    }

    for path, tokens in expectations.items():
        text = Path(path).read_text(encoding="utf-8")
        for token in tokens:
            assert token in text, f"{path} does not declare {token}"


def test_price_registry_declares_adjustment_dimensions():
    from data.storage.dimensions import get_registry

    reg = get_registry()

    expectations = {
        "ohlcv_daily": ("stock/daily/{symbol}.parquet", "akshare"),
        "ohlcv_daily_raw": ("stock/daily_raw/{symbol}.parquet", "akshare"),
        "ohlcv_daily_hfq": ("stock/daily_hfq/{symbol}.parquet", "computed"),
        "adj_factor": ("stock/adj_factor/{symbol}.parquet", "tushare_free"),
        "corporate_actions": ("stock/corporate_actions/{symbol}.parquet", "computed"),
    }
    for key, (cache, source) in expectations.items():
        dim = reg.get(key)
        assert dim is not None
        assert dim.cache == cache
        assert dim.source == source

    assert reg.get("ohlcv_daily_raw").health_enabled is False
    assert reg.get("ohlcv_daily_hfq").health_enabled is False
    assert reg.get("corporate_actions").health_enabled is False
    assert reg.validate() == []


def test_price_docs_describe_price_service_contract():
    spec = Path("docs/specs/01-data-pipeline.md").read_text(encoding="utf-8")
    schema = Path("wiki/reference/data-schema.md").read_text(encoding="utf-8")
    dimensions = Path("wiki/reference/data-dimensions.md").read_text(encoding="utf-8")

    for text in (spec, schema, dimensions):
        for token in ("PriceService", "raw", "qfq", "hfq", "corporate_actions"):
            assert token in text


def test_corporate_actions_adjust_position_for_cash_and_bonus_shares():
    from data.market.corporate_actions import apply_corporate_actions_to_position

    actions = pd.DataFrame(
        [
            {
                "symbol": "000001",
                "ex_date": "2026-01-02",
                "cash_dividend_per_share": 0.5,
                "share_multiplier": 1.2,
            }
        ]
    )

    adjusted = apply_corporate_actions_to_position(
        symbol="000001",
        shares=1000,
        cash=100.0,
        actions=actions,
        start_date="2026-01-01",
        end_date="2026-01-03",
    )

    assert adjusted.shares == 1200
    assert adjusted.cash == 600.0
    assert adjusted.events_applied == 1


def test_corporate_actions_normalizes_tushare_dividend_aliases():
    from data.market.corporate_actions import normalize_dividend_events

    raw = pd.DataFrame(
        {
            "ts_code": ["000001.SZ"],
            "ex_date": ["20260102"],
            "cash_div": [0.3],
            "stk_bo_rate": [0.1],
            "stk_co_rate": [0.2],
        }
    )

    actions = normalize_dividend_events(raw, symbol="000001")

    assert actions["symbol"].tolist() == ["000001"]
    assert actions["ex_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-02"]
    assert actions["cash_dividend_per_share"].tolist() == [0.3]
    assert actions["share_multiplier"].round(4).tolist() == [1.3]


def test_corporate_actions_load_from_datahub_path(tmp_path):
    from data.market.corporate_actions import load_corporate_actions
    from data.storage.datahub import DataHub

    hub = DataHub(store_root=tmp_path / "store", cache_root=tmp_path / "cache")
    hub.write_parquet(
        pd.DataFrame(
            {
                "symbol": ["000001"],
                "ex_date": ["2026-01-02"],
                "cash_dividend_per_share": [0.5],
                "share_multiplier": [1.0],
            }
        ),
        hub.stock_corporate_actions_path("000001"),
    )

    actions = load_corporate_actions("000001", hub=hub)

    assert actions["ex_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-02"]
    assert actions["cash_dividend_per_share"].tolist() == [0.5]
