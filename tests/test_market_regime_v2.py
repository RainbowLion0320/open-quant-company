import pandas as pd

from cybernetics import orchestrator
from cybernetics.orchestrator import MarketBreadth, MarketRegime, MarketVolume, QuantOrchestrator


def _stock_frame(last_delta: float) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=130, freq="D")
    close = [100 + i * 0.1 for i in range(130)]
    close[-1] = close[-2] + last_delta
    return pd.DataFrame({"date": dates, "close": close})


def _index_frame(direction: str = "up") -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=160, freq="D")
    if direction == "down":
        close = [200 - i * 0.4 for i in range(160)]
    else:
        close = [100 + i * 0.4 for i in range(160)]
    volume = [1000 + i for i in range(160)]
    return pd.DataFrame({"date": dates, "close": close, "volume": volume})


def _stock_volume_frame(up: bool = True) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=24, freq="D")
    close = [100 + i * 0.2 for i in range(24)]
    if not up:
        close[-5:] = [close[-6] - i * 0.2 for i in range(1, 6)]
    amount = [1000.0] * 19 + [1500.0] * 5
    return pd.DataFrame({"date": dates, "close": close, "volume": amount, "amount": amount})


def test_full_market_breadth_uses_stock_universe_files(tmp_path):
    files = []
    for symbol, delta in [("000001", 1.0), ("000002", 0.8), ("000003", -0.5)]:
        path = tmp_path / f"{symbol}.parquet"
        _stock_frame(delta).to_parquet(path, index=False)
        files.append(path)

    breadth = orchestrator._compute_full_market_breadth(files, use_cache=False)

    assert breadth.sample_size == 3
    assert breadth.up_count == 2
    assert breadth.down_count == 1
    assert breadth.advance_ratio == 2 / 3
    assert breadth.above_ma20 == 1.0
    assert breadth.above_ma60 == 1.0
    assert breadth.above_ma120 == 1.0


def test_full_market_volume_uses_market_amount_and_up_amount(tmp_path):
    files = []
    for symbol, up in [("000001", True), ("000002", True), ("000003", False)]:
        path = tmp_path / f"{symbol}.parquet"
        _stock_volume_frame(up).to_parquet(path, index=False)
        files.append(path)

    volume = orchestrator._compute_full_market_volume(files, use_cache=False)

    assert volume.sample_size == 3
    assert volume.amount_ratio_5_20 > 1.0
    assert 0.5 < volume.up_amount_ratio < 0.8


def test_regime_score_v2_combines_trend_breadth_risk_and_volume():
    bench = _index_frame("up")
    breadth = MarketBreadth(
        advance_ratio=0.72,
        above_ma20=0.80,
        above_ma60=0.75,
        above_ma120=0.68,
        sample_size=5000,
        up_count=3600,
        down_count=1300,
        unchanged_count=100,
        as_of="2026-05-20",
    )
    score, components = orchestrator._compute_regime_score_v2(
        bench,
        {"sh000001": bench, "sh000300": bench, "sz399001": bench},
        breadth,
        MarketVolume(amount_ratio_5_20=1.18, up_amount_ratio=0.68, sample_size=5000),
    )

    assert score > 65
    assert components["trend"] > 25
    assert components["breadth"] > 25
    assert components["risk"] > 10
    assert components["volume"] > 0
    assert components["risk_drawdown_raw"] > 0
    assert components["risk_volatility_raw"] > 0
    assert components["volume_up_amount_raw"] == 0.68
    assert orchestrator._classify_regime(score, components, breadth) is MarketRegime.BULL


def test_detect_returns_full_breadth_detail_and_score_components(monkeypatch):
    bench = _index_frame("up")

    def fake_index(symbol, *args, **kwargs):
        return bench

    monkeypatch.setattr("data.fetcher.get_index_daily", fake_index)
    monkeypatch.setattr(
        orchestrator,
        "_compute_full_market_breadth",
        lambda: MarketBreadth(
            advance_ratio=0.70,
            above_ma20=0.75,
            above_ma60=0.70,
            above_ma120=0.65,
            sample_size=5000,
            up_count=3500,
            down_count=1400,
            unchanged_count=100,
            as_of="2026-05-20",
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "_compute_full_market_volume",
        lambda: MarketVolume(amount_ratio_5_20=1.15, up_amount_ratio=0.70, sample_size=5000, as_of="2026-05-20"),
    )

    snapshot = QuantOrchestrator().detect()

    assert snapshot.regime is MarketRegime.BULL
    assert snapshot.breadth == 0.70
    assert snapshot.breadth_detail["sample_size"] == 5000
    assert snapshot.score_components["breadth"] > 20
    assert snapshot.score_components["volume_up_amount_raw"] == 0.70
    assert "全A上涨 70%" in snapshot.index_ma_trend
