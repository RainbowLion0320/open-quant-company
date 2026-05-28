import pandas as pd


def test_candidate_signal_row_contract():
    from signals.candidates.common import build_signal_row

    row = build_signal_row(
        symbol="000001",
        name="平安银行",
        industry="银行",
        score=82.5,
        signal="buy",
        detail={"reason": "test"},
    )

    assert row["symbol"] == "000001"
    assert row["name"] == "平安银行"
    assert row["industry"] == "银行"
    assert row["score"] == 82.5
    assert row["signal"] == "buy"
    assert row["detail"]["reason"] == "test"


def test_cross_section_percentile_score_bounds():
    from signals.candidates.common import percentile_score

    scores = percentile_score(pd.Series([10, 20, 30], index=["a", "b", "c"]))

    assert scores["a"] == 0.0
    assert scores["c"] == 100.0
    assert all(0.0 <= value <= 100.0 for value in scores.values())


def test_candidate_strategy_runners_return_signal_rows_for_small_limit():
    modules = [
        "signals.candidates.trend_following",
        "signals.candidates.donchian_breakout",
        "signals.candidates.rps_relative_strength",
        "signals.candidates.sector_rotation",
        "signals.candidates.quality_value",
        "signals.candidates.low_vol_defensive",
        "signals.candidates.volume_confirmation",
        "signals.candidates.regime_gated",
    ]

    for module_name in modules:
        module = __import__(module_name, fromlist=["compute"])
        rows = module.compute(limit=5)
        assert isinstance(rows, list)
        for row in rows:
            assert {"symbol", "name", "industry", "score", "signal", "detail"}.issubset(row)
            assert row["signal"] in {"buy", "hold", "sell"}
            assert 0 <= row["score"] <= 100
