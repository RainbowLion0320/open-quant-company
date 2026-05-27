import pandas as pd

from cybernetics import orchestrator
from web.api.services import market as market_service


def _index_frame(offset: float = 0) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=4, freq="D"),
        "close": [100 + offset, 101 + offset, 102 + offset, 103 + offset],
    })


def test_market_index_cards_are_distinct_core_indices(monkeypatch):
    def fake_load_index(symbol: str):
        frames = {
            "sh000300": _index_frame(10),
            "sz399006": _index_frame(20),
            "sh000688": _index_frame(30),
        }
        return frames[symbol], "real", "test source"

    cards = market_service.multi_asset_cards(_index_frame(), load_index_fn=fake_load_index)

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


def test_market_index_cards_respect_requested_series_limit(monkeypatch):
    def fake_load_index(symbol: str):
        return _index_frame(10), "real", "test source"

    cards = market_service.multi_asset_cards(_index_frame(), series_limit=2, load_index_fn=fake_load_index)

    assert all(len(card["series"]) == 2 for card in cards)


def test_position_capacity_uses_adaptive_regime_ceiling(monkeypatch):
    def fake_adaptive_params(regime):
        return {"max_positions": {"bull": 8, "sideways": 5, "bear": 2}[regime.value]}

    monkeypatch.setattr(orchestrator, "adaptive_params", fake_adaptive_params)

    assert market_service.position_capacity(5) == {"current": 5, "max": 8}
    assert market_service.position_capacity(10) == {"current": 10, "max": 10}


def test_macro_cards_include_liquidity_and_profit_cycle_spreads(monkeypatch):
    dates = pd.date_range("2026-01-01", periods=4, freq="MS")
    macro_frames = {
        "gdp": pd.DataFrame({"date": dates, "gdp_yoy": [4.8, 4.9, 5.1, 5.0]}),
        "pmi": pd.DataFrame({"date": dates, "pmi_mfg": [49.8, 50.2, 50.4, 50.3]}),
        "cpi": pd.DataFrame({"date": dates, "nt_yoy": [0.6, 0.8, 1.0, 1.2]}),
        "shibor": pd.DataFrame({"date": dates, "1W": [1.35, 1.38, 1.40, 1.37]}),
        "money_supply": pd.DataFrame({
            "date": dates,
            "M1_yoy": [3.5, 4.0, 5.1, 5.4],
            "M2_yoy": [8.3, 8.1, 8.6, 8.6],
        }),
        "ppi": pd.DataFrame({"date": dates, "ppi_yoy": [-0.8, -0.2, 0.5, 2.8]}),
    }

    monkeypatch.setattr(market_service, "_load_macro", lambda name: macro_frames[name])

    cards = market_service.macro_cards()
    cards_by_key = {card["key"]: card for card in cards}

    assert [card["key"] for card in cards] == [
        "gdp",
        "pmi",
        "cpi",
        "shibor",
        "m1_m2_spread",
        "ppi_cpi_spread",
    ]
    assert cards_by_key["m1_m2_spread"]["label"] == "M1-M2 Spread"
    assert cards_by_key["m1_m2_spread"]["value"] == -3.2
    assert cards_by_key["m1_m2_spread"]["prev"] == -3.5
    assert cards_by_key["m1_m2_spread"]["series"][-1] == {"date": "2026-04-01", "value": -3.2}

    assert cards_by_key["ppi_cpi_spread"]["label"] == "PPI-CPI Spread"
    assert cards_by_key["ppi_cpi_spread"]["value"] == 1.6
    assert cards_by_key["ppi_cpi_spread"]["prev"] == -0.5
    assert cards_by_key["ppi_cpi_spread"]["series"][-1] == {"date": "2026-04-01", "value": 1.6}


def test_money_supply_nat_dates_are_restored_to_month_axis():
    cached = pd.DataFrame({
        "date": [pd.NaT, pd.NaT, pd.NaT],
        "M1_yoy": [5.4, 5.1, 4.0],
        "M2_yoy": [8.6, 8.6, 8.1],
    })

    restored = market_service._restore_money_supply_dates(cached, reference_date=pd.Timestamp("2026-05-27"))

    assert restored["date"].tolist() == [
        pd.Timestamp("2026-04-01"),
        pd.Timestamp("2026-03-01"),
        pd.Timestamp("2026-02-01"),
    ]
