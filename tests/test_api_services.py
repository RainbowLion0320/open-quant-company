import pandas as pd

from cybernetics import orchestrator
from cybernetics.regime import MarketRegime
from web.api.services import market as market_service
from web.api.services import sectors as sector_service


def _index_frame(offset: float = 0) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=4, freq="D"),
        "close": [100 + offset, 101 + offset, 102 + offset, 103 + offset],
    })


def test_market_service_index_cards_are_distinct_core_indices():
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
    assert {"A股核心", "黄金ETF", "10Y国债"}.isdisjoint({c["label"] for c in cards})

    signatures = {
        tuple((point["date"], point["value"]) for point in c["series"])
        for c in cards
    }
    assert len(signatures) == 4


def test_market_service_index_cards_respect_requested_series_limit():
    cards = market_service.multi_asset_cards(
        _index_frame(),
        series_limit=2,
        load_index_fn=lambda symbol: (_index_frame(10), "real", "test source"),
    )

    assert all(len(card["series"]) == 2 for card in cards)


def test_market_service_position_capacity_uses_adaptive_regime_ceiling(monkeypatch):
    def fake_adaptive_params(regime):
        return {"max_positions": {"bull": 8, "sideways": 5, "bear": 2}[regime.value]}

    monkeypatch.setattr(orchestrator, "adaptive_params", fake_adaptive_params)

    assert market_service.position_capacity(5) == {"current": 5, "max": 8}
    assert market_service.position_capacity(10) == {"current": 10, "max": 10}


def test_market_regime_payload_includes_raw_and_stability_state():
    class Snapshot:
        regime = MarketRegime.BULL
        raw_regime = MarketRegime.BEAR
        regime_score = 62.5
        index_ma_trend = "unit"
        volume_trend = "normal"
        breadth = 0.62
        breadth_detail = {"sample_size": 5000}
        score_components = {"trend_raw": 0.56}
        regime_state = {
            "raw_value": "bear",
            "confirmed_value": "bull",
            "pending_value": "bear",
            "pending_count": 1,
            "min_dwell": 3,
            "confirmed_changed": False,
        }

    payload = market_service.regime_payload(Snapshot())

    assert payload["value"] == "bull"
    assert payload["raw_value"] == "bear"
    assert payload["stability"]["pending_value"] == "bear"
    assert payload["stability"]["pending_count"] == 1
    assert payload["stability"]["min_dwell"] == 3


def test_sector_service_source_summary_prioritizes_real_then_proxy():
    assert sector_service.source_summary([{"data_source": "proxy"}, {"data_source": "real"}]) == "real"
    assert sector_service.source_summary([{"data_source": "proxy"}]) == "proxy"
    assert sector_service.source_summary([]) == "missing"
