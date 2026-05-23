import pandas as pd

from web.api.routes import market


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

    monkeypatch.setattr(market, "_load_index", fake_load_index)

    cards = market._multi_asset_cards(_index_frame())

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
