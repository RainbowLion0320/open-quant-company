from cybernetics.regime_scoring import (
    breadth_strength,
    classify_regime_value,
    compose_regime_score,
    volume_strength,
)


def test_regime_facade_normalizes_enum_and_string_values():
    from cybernetics.regime import MarketRegime, normalize_regime, to_market_regime

    assert normalize_regime(MarketRegime.BULL) == "bull"
    assert normalize_regime("BEAR") == "bear"
    assert normalize_regime("not-a-regime") == "sideways"
    assert to_market_regime("bull") is MarketRegime.BULL


def test_trend_regime_detector_uses_shared_facade():
    import pandas as pd
    from cybernetics.regime import MarketRegime, detect_trend_regime

    close = list(range(1, 80))
    df = pd.DataFrame({"close": close})

    assert detect_trend_regime({"sh000001": df}) is MarketRegime.BULL


def test_breadth_strength_weights_market_participation():
    assert breadth_strength(0.72, 0.80, 0.75, 0.68) == 0.7475
    assert breadth_strength(-1.0, 2.0, 0.5, 0.5) == 0.425


def test_volume_strength_combines_activity_up_amount_and_index_confirmation():
    strength, trend, detail = volume_strength(
        amount_ratio_5_20=1.18,
        advance_ratio=0.72,
        up_amount_ratio=0.68,
        index_volume=0.62,
        sample_size=5000,
        amount_5d=1_000_000,
        amount_20d=900_000,
        volume_expansion=1.2,
        volume_contraction=0.8,
        index_detail={"volume_ratio_sh000001": 1.1},
    )

    assert trend == "正常"
    assert strength > 0.60
    assert detail["volume_up_amount_raw"] == 0.68
    assert detail["volume_ratio_sh000001"] == 1.1


def test_compose_regime_score_uses_validated_production_weights():
    score, components = compose_regime_score(
        trend_raw=0.8,
        breadth_raw=0.75,
        risk_raw=0.7,
        volume_raw=0.6,
        sample_size=5000,
        index_trend={"sh000001": 0.8},
        risk_detail={"risk_drawdown_raw": 0.7},
        volume_detail={"volume_up_amount_raw": 0.68},
    )

    assert score == 73.5
    assert components["trend"] == 24.0
    assert components["breadth"] == 22.5
    assert components["risk"] == 21.0
    assert components["volume"] == 6.0
    assert components["trend_sh000001"] == 0.8


def test_classify_regime_value_uses_score_trend_and_breadth_gates():
    assert classify_regime_value(70, trend_raw=0.60, breadth_raw=0.70, advance_ratio=0.58) == "bull"
    assert classify_regime_value(70, trend_raw=0.50, breadth_raw=0.70, advance_ratio=0.58) == "sideways"
    assert classify_regime_value(62, trend_raw=0.60, breadth_raw=0.70, advance_ratio=0.58) == "bull"
    assert classify_regime_value(39, trend_raw=0.50, breadth_raw=0.50, advance_ratio=0.45) == "bear"
    assert classify_regime_value(50, trend_raw=0.35, breadth_raw=0.35, advance_ratio=0.45) == "bear"
