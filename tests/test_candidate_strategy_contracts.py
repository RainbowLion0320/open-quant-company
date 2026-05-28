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
