import pandas as pd

from cybernetics import orchestrator
from cybernetics.orchestrator import MarketBreadth, MarketRegime, MarketVolume, QuantOrchestrator


def _force_regime_engine(monkeypatch, engine: str) -> None:
    original_load_config = orchestrator._load_config

    def fake_load_config():
        cfg = dict(original_load_config())
        hmm_cfg = dict(cfg.get("hmm", {}))
        hmm_cfg.pop("regime_engine", None)
        cfg["hmm"] = hmm_cfg
        cfg["regime_engine"] = engine
        return cfg

    monkeypatch.setattr(orchestrator, "_load_config", fake_load_config)


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


def test_regime_indexes_reflect_config_changes_without_module_reload(monkeypatch):
    orchestrator._REGIME_INDEXES = None

    monkeypatch.setattr(
        "core.settings.get_section",
        lambda key, default=None: {"sh000001": 1.0} if key == "cybernetics.regime_indexes" else default,
    )
    first = orchestrator._regime_indexes()

    monkeypatch.setattr(
        "core.settings.get_section",
        lambda key, default=None: {"sh000001": 0.1} if key == "cybernetics.regime_indexes" else default,
    )
    second = orchestrator._regime_indexes()

    assert dict((symbol, weight) for symbol, _label, weight in first)["sh000001"] == 1.0
    assert dict((symbol, weight) for symbol, _label, weight in second)["sh000001"] == 0.1


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


def test_regime_score_combines_validated_trend_breadth_risk_and_volume():
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
    assert components["trend"] > 20
    assert components["breadth"] > 20
    assert components["risk"] > 15
    assert components["volume"] > 0
    assert components["risk_drawdown_raw"] > 0
    assert components["risk_volatility_raw"] > 0
    assert components["volume_up_amount_raw"] == 0.68
    assert orchestrator._classify_regime(score, components, breadth) is MarketRegime.BULL


def test_detect_returns_full_breadth_detail_and_score_components(monkeypatch):
    orchestrator.reset_regime_transition_state()
    _force_regime_engine(monkeypatch, "rule_based")
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


def test_detect_applies_min_dwell_across_request_scoped_orchestrators(monkeypatch):
    orchestrator.reset_regime_transition_state()
    _force_regime_engine(monkeypatch, "rule_based")
    bench = _index_frame("up")

    def fake_index(symbol, *args, **kwargs):
        return bench

    raw_sequence = iter([
        MarketRegime.BULL,
        MarketRegime.BEAR,
        MarketRegime.BEAR,
        MarketRegime.BEAR,
    ])

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
    monkeypatch.setattr(
        orchestrator,
        "_compute_regime_score_v2",
        lambda *args, **kwargs: (35.0, {"trend_raw": 0.30, "breadth_raw": 0.35, "risk_raw": 0.45, "volume_raw": 0.50}),
    )
    monkeypatch.setattr(orchestrator, "_classify_regime", lambda *args, **kwargs: next(raw_sequence))
    observation_keys = iter(["2026-05-20", "2026-05-21", "2026-05-22", "2026-05-23"])
    monkeypatch.setattr(orchestrator, "_regime_observation_key", lambda *args, **kwargs: next(observation_keys))

    detected = [QuantOrchestrator().detect().regime for _ in range(4)]

    assert detected == [
        MarketRegime.BULL,
        MarketRegime.BULL,
        MarketRegime.BULL,
        MarketRegime.BEAR,
    ]


def test_detect_exposes_raw_and_stabilized_regime_metadata(monkeypatch):
    orchestrator.reset_regime_transition_state()
    _force_regime_engine(monkeypatch, "rule_based")
    bench = _index_frame("up")

    monkeypatch.setattr("data.fetcher.get_index_daily", lambda *args, **kwargs: bench)
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
    monkeypatch.setattr(
        orchestrator,
        "_compute_regime_score_v2",
        lambda *args, **kwargs: (35.0, {"trend_raw": 0.30, "breadth_raw": 0.35, "risk_raw": 0.45, "volume_raw": 0.50}),
    )
    raw_sequence = iter([MarketRegime.BULL, MarketRegime.BEAR])
    monkeypatch.setattr(orchestrator, "_classify_regime", lambda *args, **kwargs: next(raw_sequence))
    observation_keys = iter(["2026-05-20", "2026-05-21"])
    monkeypatch.setattr(orchestrator, "_regime_observation_key", lambda *args, **kwargs: next(observation_keys))

    QuantOrchestrator().detect()
    snapshot = QuantOrchestrator().detect()

    assert snapshot.regime is MarketRegime.BULL
    assert snapshot.raw_regime is MarketRegime.BEAR
    assert snapshot.regime_state["raw_value"] == "bear"
    assert snapshot.regime_state["confirmed_value"] == "bull"
    assert snapshot.regime_state["pending_value"] == "bear"
    assert snapshot.regime_state["pending_count"] == 1
    assert snapshot.regime_state["min_dwell"] == 3


def test_resolve_regime_decision_uses_high_confidence_hmm_override():
    decision = orchestrator._resolve_regime_decision(
        rule_raw_regime=MarketRegime.BULL,
        hmm_raw_regime=MarketRegime.BEAR,
        regime_probs={"bull": 0.05, "sideways": 0.10, "bear": 0.85},
        hmm_confidence=0.85,
        engine="hybrid",
    )

    assert decision.raw_regime is MarketRegime.BEAR
    assert decision.detection_method == "hmm"
    assert decision.regime_probs["bear"] == 0.85
    assert decision.decision_reason == "hmm_high_confidence_override"


def test_resolve_regime_decision_blends_low_confidence_disagreement():
    decision = orchestrator._resolve_regime_decision(
        rule_raw_regime=MarketRegime.BULL,
        hmm_raw_regime=MarketRegime.BEAR,
        regime_probs={"bull": 0.15, "sideways": 0.30, "bear": 0.55},
        hmm_confidence=0.55,
        engine="hybrid",
    )

    assert decision.raw_regime is MarketRegime.BULL
    assert decision.detection_method == "hybrid"
    assert decision.regime_probs["bull"] > decision.regime_probs["bear"]
    assert round(sum(decision.regime_probs.values()), 6) == 1
    assert decision.decision_reason == "hybrid_low_confidence_blend"


def test_detect_uses_hybrid_probabilities_for_adaptive_params(monkeypatch):
    orchestrator.reset_regime_transition_state()
    _force_regime_engine(monkeypatch, "hybrid")
    bench = _index_frame("up")

    monkeypatch.setattr("data.fetcher.get_index_daily", lambda *args, **kwargs: bench)
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
    monkeypatch.setattr(
        orchestrator,
        "_compute_regime_score_v2",
        lambda *args, **kwargs: (68.0, {"trend_raw": 0.70, "breadth_raw": 0.75, "risk_raw": 0.65, "volume_raw": 0.60}),
    )
    monkeypatch.setattr(orchestrator, "_classify_regime", lambda *args, **kwargs: MarketRegime.BULL)
    monkeypatch.setattr(
        orchestrator,
        "_hmm_detect",
        lambda *args, **kwargs: (
            {"bull": 0.15, "sideways": 0.30, "bear": 0.55},
            0.55,
            0.98,
            MarketRegime.BEAR,
        ),
    )

    qo = QuantOrchestrator()
    snapshot = qo.detect()

    assert snapshot.detection_method == "hybrid"
    assert snapshot.raw_regime is MarketRegime.BULL
    assert qo.params["position_size"] < 0.30
    assert qo.params["position_size"] > 0.05
    expected = sum(
        snapshot.regime_probs[key] * {"bull": 0.30, "sideways": 0.15, "bear": 0.05}[key]
        for key in ("bull", "sideways", "bear")
    )
    assert round(qo.params["position_size"], 6) == round(expected, 6)
