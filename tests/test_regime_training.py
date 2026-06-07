import json

import numpy as np
import pandas as pd
import pytest


def test_forward_labels_use_future_rows_only():
    from research.regime.features import build_forward_labels

    dates = pd.date_range("2026-01-01", periods=8, freq="D")
    close = pd.Series([100, 101, 102, 99, 98, 103, 106, 104], index=dates, name="close")

    labels = build_forward_labels(close, horizons=(2,))

    assert labels.loc[dates[0], "future_2d_return"] == pytest.approx(0.02)
    assert labels.loc[dates[0], "future_2d_max_drawdown"] == 0.0
    assert labels.loc[dates[2], "future_2d_return"] == pytest.approx(98 / 102 - 1)
    assert pd.isna(labels.loc[dates[-1], "future_2d_return"])


def test_candidate_policy_classifies_with_hysteresis_and_min_dwell():
    from research.regime_types import RegimePolicy
    from research.regime.policies import apply_policy

    features = pd.DataFrame(
        {
            "trend_raw": [0.70, 0.69, 0.52, 0.68, 0.30, 0.28],
            "breadth_raw": [0.70, 0.68, 0.51, 0.66, 0.30, 0.28],
            "risk_raw": [0.80, 0.75, 0.50, 0.70, 0.20, 0.20],
            "volume_raw": [0.55, 0.55, 0.50, 0.55, 0.30, 0.30],
            "advance_ratio": [0.60, 0.59, 0.50, 0.58, 0.35, 0.34],
        },
        index=pd.date_range("2026-01-01", periods=6, freq="D"),
    )
    policy = RegimePolicy(
        candidate_id="test",
        weights={"trend": 0.35, "breadth": 0.35, "risk": 0.20, "volume": 0.10},
        bull_threshold=65,
        bear_threshold=35,
        trend_confirm=0.55,
        breadth_confirm=0.55,
        bear_trend_breakdown=0.40,
        bear_breadth_breakdown=0.40,
        min_dwell=2,
    )

    result = apply_policy(features, policy)

    assert list(result["regime"]) == ["bull", "bull", "bull", "bull", "bear", "bear"]
    assert result["score"].iloc[0] > 65


def test_walk_forward_splits_are_time_ordered():
    from research.regime.policies import walk_forward_splits

    dates = pd.date_range("2018-01-31", "2023-12-31", freq="ME")
    splits = list(walk_forward_splits(dates, train_years=3, validate_years=1))

    assert splits
    for train_idx, validate_idx in splits:
        assert max(train_idx) < min(validate_idx)
        assert len(validate_idx) >= 10


def test_challenger_must_clear_promotion_gates():
    from research.regime_types import PromotionGateResult
    from research.regime.evaluation import decide_promotion

    result = decide_promotion(
        champion_score=70.0,
        challenger_score=73.0,
        challenger_maxdd_delta=0.0,
        challenger_turnover_delta=0.03,
        beats_baselines=True,
        valid_year_win_rate=0.70,
    )

    assert result == PromotionGateResult.RECOMMEND_CHALLENGER_FOR_REVIEW


def test_collapsed_regime_policy_cannot_clear_promotion_gates():
    from research.regime_types import PromotionGateResult
    from research.regime.evaluation import decide_promotion

    result = decide_promotion(
        champion_score=20.0,
        challenger_score=60.0,
        challenger_maxdd_delta=0.05,
        challenger_turnover_delta=-0.50,
        beats_baselines=True,
        valid_year_win_rate=0.80,
        regime_diversified=False,
    )

    assert result == PromotionGateResult.KEEP_CHAMPION


def test_candidate_ranking_penalizes_excessive_flipping():
    from research.regime.evaluation import rank_candidate_rows

    rows = [
        {"candidate_id": "stable", "predictive_score": 70, "strategy_score": 65, "turnovers": 8, "complexity": 2},
        {"candidate_id": "noisy", "predictive_score": 72, "strategy_score": 66, "turnovers": 80, "complexity": 4},
    ]

    ranked = rank_candidate_rows(rows)

    assert ranked[0]["candidate_id"] == "stable"


def test_report_summary_schema_is_stable(tmp_path):
    from research.regime.reports import write_regime_training_report

    result = {
        "decision": "keep_champion",
        "champion_score": 50.0,
        "best_challenger_score": 51.0,
        "best_challenger_id": "w0001",
        "candidate_rows": [],
        "walk_forward_rows": [],
        "strategy_rows": [],
        "stability_rows": [],
        "notes": ["schema smoke"],
    }

    summary = write_regime_training_report(tmp_path, result)

    assert summary["decision"] == "keep_champion"
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "champion_vs_challenger.md").exists()
    assert json.loads((tmp_path / "summary.json").read_text())["status"] == "ok"


def test_strategy_ab_rows_include_required_baselines():
    from research.regime_types import RegimePolicy
    from research.regime.evaluation import run_regime_research

    dates = pd.date_range("2018-01-01", periods=1400, freq="B")
    close = pd.Series(100 + pd.RangeIndex(len(dates)).to_series().to_numpy() * 0.02, index=dates)
    features = pd.DataFrame(
        {
            "trend_raw": 0.62,
            "breadth_raw": 0.58,
            "risk_raw": 0.70,
            "volume_raw": 0.52,
            "advance_ratio": 0.57,
        },
        index=dates,
    )
    policies = [
        RegimePolicy("trend_only_baseline", {"trend": 1.0}),
        RegimePolicy("trend_breadth_baseline", {"trend": 0.55, "breadth": 0.45}),
        RegimePolicy("challenger", {"trend": 0.35, "breadth": 0.35, "risk": 0.20, "volume": 0.10}),
    ]

    result = run_regime_research(features, close, policies=policies)
    strategy_names = {row["strategy"] for row in result["strategy_rows"]}

    assert {
        "no_regime_fixed_allocation",
        "champion_current_formula",
        "trend_only_baseline",
        "trend_breadth_baseline",
        "best_challenger",
    }.issubset(strategy_names)


def test_observation_frame_matches_matrix_rows_after_standardisation():
    from cybernetics.features import build_observation_frame, build_observation_matrix, build_regime_features

    dates = pd.date_range("2020-01-01", periods=320, freq="B")
    close = pd.Series(100 + np.arange(len(dates)) * 0.2, index=dates)
    frame = pd.DataFrame({"close": close, "volume": 1000.0, "amount": close * 1000.0}, index=dates)
    features = build_regime_features({"sh000001": frame})

    observations = build_observation_frame(features)
    matrix, _ = build_observation_matrix(features)

    assert len(observations) == len(matrix)
    assert observations.index[0] > features.index[0]


def test_forward_return_alignment_uses_observation_index_after_standardisation():
    from cybernetics.features import build_observation_frame, build_regime_features
    from scripts.train_regime_hmm import _align_forward_returns_to_observations

    dates = pd.date_range("2020-01-01", periods=320, freq="B")
    close = pd.Series(100 + np.arange(len(dates)) * 0.2, index=dates)
    frame = pd.DataFrame({"close": close, "volume": 1000.0, "amount": close * 1000.0}, index=dates)
    features = build_regime_features({"sh000001": frame})

    observations = build_observation_frame(features)
    aligned = _align_forward_returns_to_observations(features, close)
    expected = close.pct_change(20).shift(-20).reindex(observations.index).fillna(0.0).to_numpy()

    assert len(aligned) == len(observations)
    assert aligned[0] == pytest.approx(expected[0])
