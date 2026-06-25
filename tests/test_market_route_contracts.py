import pandas as pd

from data.market.assets import overview as asset_overview
from tests.market_helpers import fake_core_index_loader, market_index_frame
from web.api.services import market as market_service


def test_market_index_cards_are_distinct_core_indices():
    cards = market_service.multi_asset_cards(market_index_frame(), load_index_fn=fake_core_index_loader)

    assert [c["key"] for c in cards] == ["sse", "csi300", "chinext", "star50"]
    assert [c["label"] for c in cards] == ["上证综指", "沪深300", "创业板指", "科创50"]
    assert [c["symbol"] for c in cards] == ["000001.SH", "000300.SH", "399006.SZ", "000688.SH"]

    old_labels = {"A股核心", "黄金ETF", "10Y国债"}
    assert old_labels.isdisjoint({c["label"] for c in cards})

    signatures = {
        tuple((point["date"], point["value"]) for point in c["series"])
        for c in cards
    }
    assert len(signatures) == 4


def test_market_index_cards_respect_requested_series_limit():
    def fake_load_index(symbol: str):
        return market_index_frame(10), "real", "test source"

    cards = market_service.multi_asset_cards(market_index_frame(), series_limit=2, load_index_fn=fake_load_index)

    assert all(len(card["series"]) == 2 for card in cards)


def test_asset_pulse_cards_merge_local_series_with_asset_chain_readiness(monkeypatch):
    overview_items = [
        {
            "asset_type": "stock",
            "label": "股票",
            "data_source": "tushare",
            "data_status": "ready",
            "strategy_status": "ready",
            "backtest_status": "ready",
            "paper_status": "ready",
            "live_status": "configured_contract",
            "universe_size": 5100,
            "blockers": [],
        },
        {
            "asset_type": "etf",
            "label": "ETF",
            "data_source": "akshare",
            "data_status": "ready",
            "strategy_status": "ready",
            "backtest_status": "ready",
            "paper_status": "ready",
            "live_status": "blocked",
            "universe_size": 800,
            "blockers": ["live_adapter_not_configured"],
        },
        {
            "asset_type": "crypto",
            "label": "加密货币",
            "data_source": "akshare",
            "data_status": "blocked",
            "strategy_status": "blocked",
            "backtest_status": "blocked",
            "paper_status": "blocked",
            "live_status": "blocked",
            "universe_size": 2,
            "blockers": ["crypto_data_stale_until_fresh_source"],
        },
    ]
    local_prices = pd.DataFrame({
        "date": pd.date_range("2026-06-01", periods=3, freq="D"),
        "close": [100.0, 101.0, 103.0],
    })

    monkeypatch.setattr(asset_overview, "asset_overview_items", lambda: overview_items)
    monkeypatch.setattr(market_service, "_local_asset_frame", lambda asset_type, symbol: local_prices)

    cards = market_service.asset_pulse_cards([
        {
            "key": "sse",
            "label": "上证综指",
            "symbol": "000001.SH",
            "value": 3100.0,
            "change": 10.0,
            "change_pct": 0.32,
            "unit": "",
            "series": [{"date": "2026-06-01", "value": 3090.0}, {"date": "2026-06-02", "value": 3100.0}],
            "data_source": "real",
            "source_detail": "unit",
        }
    ])
    by_asset = {card["asset_type"]: card for card in cards}

    assert list(by_asset) == ["stock", "etf", "crypto"]
    assert by_asset["stock"]["key"] == "stock"
    assert by_asset["stock"]["value"] == 3100.0
    assert by_asset["stock"]["readiness_score"] == 5
    assert by_asset["etf"]["value"] == 103.0
    assert by_asset["etf"]["readiness_score"] == 4
    assert by_asset["etf"]["blockers"] == ["live_adapter_not_configured"]
    assert by_asset["crypto"]["data_status"] == "blocked"
    assert by_asset["crypto"]["blockers"] == ["crypto_data_stale_until_fresh_source"]


def test_asset_pulse_local_cache_read_is_fail_closed_for_display_symbols():
    frame = market_service._local_asset_frame("crypto", "BTC/USDT")

    assert frame.empty
    assert list(frame.columns) == ["date", "close"]


def test_asset_market_modules_are_asset_specific(monkeypatch, tmp_path):
    overview_items = [
        {"asset_type": "etf", "label": "ETF", "universe_size": 51, "blockers": []},
        {"asset_type": "bond", "label": "债券", "universe_size": 9, "blockers": ["convertible_bond_only"]},
        {"asset_type": "futures", "label": "期货", "universe_size": 11, "blockers": ["live_adapter_not_configured"]},
        {"asset_type": "crypto", "label": "加密货币", "universe_size": 5, "blockers": ["crypto_data_stale_until_fresh_source"]},
    ]
    etf_prices = pd.DataFrame({
        "date": pd.date_range("2026-06-01", periods=3, freq="D"),
        "close": [1.0, 1.02, 1.05],
    })
    yield_curve = pd.DataFrame({
        "date": pd.date_range("2026-06-01", periods=2, freq="D"),
        "中国国债收益率2年": [1.2, 1.3],
        "中国国债收益率5年": [1.5, 1.6],
        "中国国债收益率10年": [1.7, 1.8],
        "中国国债收益率30年": [2.1, 2.2],
    })
    futures_prices = pd.DataFrame({
        "date": pd.date_range("2026-06-01", periods=3, freq="D"),
        "close": [4000.0, 4050.0, 4100.0],
    })

    monkeypatch.setattr(market_service, "_asset_overview_by_type", lambda: {item["asset_type"]: item for item in overview_items})
    monkeypatch.setattr(market_service, "_fund_daily_frame", lambda symbol: etf_prices)
    monkeypatch.setattr(market_service, "_futures_daily_frame", lambda symbol: futures_prices)

    class DummyHub:
        def store_dir(self, asset_type):
            return tmp_path / asset_type

        def read_parquet(self, path, default=None):
            return yield_curve

    monkeypatch.setattr(market_service, "HUB", DummyHub())
    (tmp_path / "bond").mkdir()
    (tmp_path / "bond" / "treasury_yields.parquet").touch()

    modules = {module["asset_type"]: module for module in market_service.asset_market_modules(series_limit=3)}

    assert list(modules) == ["etf", "bond", "futures", "crypto"]
    assert modules["etf"]["kind"] == "fund_rotation"
    assert modules["etf"]["series"]
    assert modules["bond"]["kind"] == "rate_curve"
    assert [point["tenor"] for point in modules["bond"]["curve"]] == ["2Y", "5Y", "10Y", "30Y"]
    assert modules["futures"]["kind"] == "contract_movers"
    assert modules["futures"]["items"]
    assert modules["crypto"]["kind"] == "risk_sentinel"
    assert modules["crypto"]["status"] == "blocked"


def test_market_overview_exposes_asset_modules_without_asset_chain():
    payload = market_service.build_market_overview("6M")

    assert {module["asset_type"] for module in payload["asset_modules"]} == {"etf", "bond", "futures", "crypto"}
    assert "asset_chain" not in payload
