import json

import pandas as pd
import pytest


def _asset_panel(periods: int = 320, start: str = "2018-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=periods, freq="B")
    seasonal = [0.004 if (i // 80) % 2 == 0 else -0.002 for i in range(periods)]
    equity_close = pd.Series(100.0, index=dates)
    for i in range(1, periods):
        equity_close.iloc[i] = equity_close.iloc[i - 1] * (1.0 + seasonal[i])
    panel = pd.DataFrame(index=dates)
    panel["equity_close"] = equity_close
    panel["equity_return"] = panel["equity_close"].pct_change().fillna(0.0)
    panel["cash_return"] = 0.0
    panel["defensive_return"] = 0.0002
    panel.attrs["asset_sources"] = {"equity": "synthetic", "defensive": "synthetic_bond", "cash": "zero_cash"}
    panel.attrs["notes"] = []
    return panel


def _features(index: pd.DatetimeIndex) -> pd.DataFrame:
    cycle = pd.Series(range(len(index)), index=index)
    risk_on = ((cycle // 80) % 2 == 0).astype(float)
    risk_off = 1.0 - risk_on
    return pd.DataFrame(
        {
            "trend_raw": 0.70 * risk_on + 0.30 * risk_off,
            "breadth_raw": 0.68 * risk_on + 0.32 * risk_off,
            "risk_raw": 0.75 * risk_on + 0.25 * risk_off,
            "volume_raw": 0.55,
            "advance_ratio": 0.62 * risk_on + 0.38 * risk_off,
        },
        index=index,
    )


def test_tradable_asset_panel_cash_fallback_has_sources_and_returns():
    from research.regime_training import build_tradable_asset_panel

    dates = pd.date_range("2026-01-01", periods=4, freq="B")
    equity = pd.DataFrame({"date": dates, "close": [100.0, 101.0, 99.0, 102.0]})

    panel = build_tradable_asset_panel(equity, start="2026-01-01", end="2026-01-06")

    assert list(panel.columns) == ["equity_close", "equity_return", "cash_return", "defensive_return"]
    assert panel["equity_return"].iloc[1] == pytest.approx(0.01)
    assert panel["cash_return"].eq(0.0).all()
    assert panel["defensive_return"].eq(0.0).all()
    assert panel.attrs["asset_sources"]["defensive"] == "cash_fallback"
    assert "defensive_unavailable" in panel.attrs["notes"]


def test_treasury_defensive_proxy_handles_date_index_and_column(tmp_path):
    from research.regime_training import _load_treasury_defensive_proxy

    bond_dir = tmp_path / "var/store/bond"
    bond_dir.mkdir(parents=True)
    dates = pd.date_range("2026-01-01", periods=4, freq="B")
    frame = pd.DataFrame({"日期": dates, "中国国债收益率10年": [2.0, 2.01, 2.0, 1.99]}, index=dates)
    frame.index.name = "date"
    frame.to_parquet(bond_dir / "treasury_yields.parquet")

    proxy, source, notes = _load_treasury_defensive_proxy(data_root=tmp_path)

    assert source == "cn_10y_treasury_proxy"
    assert notes == []
    assert list(proxy.columns) == ["date", "close"]
    assert len(proxy) == 4


def test_profit_labels_use_future_rows_without_lookahead():
    from research.regime_training import build_profit_labels

    panel = _asset_panel(periods=8)
    panel.loc[panel.index[1], "equity_close"] = 90.0
    panel.loc[panel.index[2], "equity_close"] = 110.0
    panel["equity_return"] = panel["equity_close"].pct_change().fillna(0.0)
    panel["cash_return"] = 0.0
    panel["defensive_return"] = 0.001

    labels = build_profit_labels(panel, horizons=(2,))

    assert labels.loc[panel.index[0], "future_2d_equity_return"] == pytest.approx(0.10)
    assert labels.loc[panel.index[0], "future_2d_equity_max_drawdown"] == pytest.approx(-0.10)
    defensive_total = (1.001 * 1.001) - 1.0
    assert labels.loc[panel.index[0], "future_2d_defensive_excess_return"] == pytest.approx(0.10 - defensive_total)
    assert pd.isna(labels.loc[panel.index[-1], "future_2d_equity_return"])


def test_tradable_exposure_uses_prior_day_regime_for_returns():
    from research.regime_training import DEFAULT_EXPOSURE_MAP, simulate_tradable_exposure

    dates = pd.date_range("2026-01-01", periods=4, freq="B")
    panel = pd.DataFrame(
        {
            "equity_close": [100.0, 110.0, 99.0, 99.0],
            "equity_return": [0.0, 0.10, -0.10, 0.0],
            "cash_return": 0.0,
            "defensive_return": [0.0, 0.0, 0.02, 0.0],
        },
        index=dates,
    )
    regimes = pd.Series(["risk_on", "risk_off", "neutral", "risk_on"], index=dates)

    metrics = simulate_tradable_exposure(panel, regimes, DEFAULT_EXPOSURE_MAP)

    daily = metrics["daily_return"]
    assert daily.loc[dates[1]] == pytest.approx(0.08)
    assert daily.loc[dates[2]] == pytest.approx(0.10 * -0.10 + 0.90 * 0.02)
    assert metrics["risk_on_ratio"] == pytest.approx(0.50)
    assert metrics["risk_off_ratio"] == pytest.approx(0.25)
    assert metrics["turnover_proxy"] > 0


def test_profit_score_penalizes_permanent_defense_and_gates_reject_it():
    from research.regime_training import decide_profit_promotion, profit_score_candidate

    good_metrics = {
        "cagr": 0.12,
        "sharpe": 1.1,
        "calmar": 1.4,
        "max_drawdown": -0.09,
        "turnover_proxy": 4.0,
        "risk_on_ratio": 0.30,
        "neutral_ratio": 0.45,
        "risk_off_ratio": 0.25,
    }
    collapsed_metrics = {**good_metrics, "risk_on_ratio": 0.0, "neutral_ratio": 0.0, "risk_off_ratio": 1.0}
    baselines = [{"strategy": "fixed_60_40", "calmar": 0.6, "sharpe": 0.7, "cagr": 0.06, "max_drawdown": -0.12}]

    diverse = profit_score_candidate(good_metrics, baselines, complexity=1)
    collapsed = profit_score_candidate(collapsed_metrics, baselines, complexity=1)

    assert diverse["profit_score"] > collapsed["profit_score"]
    assert decide_profit_promotion(
        champion_metrics={"calmar": 0.9, "sharpe": 0.8, "cagr": 0.08, "max_drawdown": -0.10},
        challenger_metrics=collapsed_metrics,
        baseline_rows=baselines,
        walk_forward_rows=[{"winner": "challenger"}] * 4,
    ).value == "keep_champion"


def test_v3_gate_diagnostics_apply_to_champion_and_candidates():
    from research.regime_training import build_profit_gate_diagnostics

    candidate_rows = [
        {
            "candidate_id": "champion_current_formula",
            "cagr": 0.04,
            "sharpe": 0.60,
            "calmar": 0.50,
            "max_drawdown": -0.08,
            "turnover_proxy": 316.0,
            "risk_on_ratio": 0.16,
            "neutral_ratio": 0.60,
            "risk_off_ratio": 0.24,
            "profit_score": 10.0,
        },
        {
            "candidate_id": "low_participation_winner",
            "cagr": 0.07,
            "sharpe": 1.10,
            "calmar": 1.40,
            "max_drawdown": -0.05,
            "turnover_proxy": 40.0,
            "risk_on_ratio": 0.06,
            "neutral_ratio": 0.68,
            "risk_off_ratio": 0.26,
            "profit_score": 64.0,
        },
        {
            "candidate_id": "permanent_defense",
            "cagr": 0.06,
            "sharpe": 1.20,
            "calmar": 1.00,
            "max_drawdown": -0.06,
            "turnover_proxy": 0.0,
            "risk_on_ratio": 0.0,
            "neutral_ratio": 0.0,
            "risk_off_ratio": 1.0,
            "profit_score": 50.0,
        },
    ]
    baseline_rows = [
        {"strategy": "buy_and_hold_equity", "cagr": 0.02, "sharpe": 0.20, "calmar": 0.10, "max_drawdown": -0.30},
        {"strategy": "fixed_60_40", "cagr": 0.03, "sharpe": 0.35, "calmar": 0.18, "max_drawdown": -0.17},
        {"strategy": "ma_20_60_timing", "cagr": 0.02, "sharpe": 0.30, "calmar": 0.20, "max_drawdown": -0.11},
    ]
    validation_rows = [
        {
            "candidate_id": "low_participation_winner",
            "oos_windows": 7,
            "oos_win_rate_vs_champion": 0.70,
            "oos_profit_score_delta_mean": 5.0,
            "oos_calmar_mean": 1.0,
            "oos_sharpe_mean": 0.9,
            "oos_cagr_mean": 0.06,
        },
        {
            "candidate_id": "permanent_defense",
            "oos_windows": 7,
            "oos_win_rate_vs_champion": 0.90,
            "oos_profit_score_delta_mean": 10.0,
            "oos_calmar_mean": 1.2,
            "oos_sharpe_mean": 1.0,
            "oos_cagr_mean": 0.06,
        },
    ]

    diagnostics = build_profit_gate_diagnostics(candidate_rows, candidate_rows[0], baseline_rows, validation_rows)
    by_id = {row["candidate_id"]: row for row in diagnostics}

    assert by_id["champion_current_formula"]["role"] == "champion"
    assert by_id["champion_current_formula"]["passes_validation"] is True
    assert "low_risk_on_participation" in by_id["low_participation_winner"]["warnings"]
    assert by_id["low_participation_winner"]["passes_validation"] is True
    assert by_id["permanent_defense"]["passes_validation"] is False
    assert "permanent_regime_collapse" in by_id["permanent_defense"]["failed_gates"]


def test_v3_selects_best_validated_candidate_after_skipping_invalid_top_candidate():
    from research.regime_training import select_best_validated_formula

    candidate_rows = [
        {"candidate_id": "invalid_top", "profit_score": 90.0, "calmar": 2.0},
        {"candidate_id": "validated_second", "profit_score": 70.0, "calmar": 1.0},
        {"candidate_id": "champion_current_formula", "profit_score": 50.0, "calmar": 0.5},
    ]
    gate_rows = [
        {"candidate_id": "invalid_top", "passes_validation": False, "failed_gates": "permanent_regime_collapse"},
        {"candidate_id": "validated_second", "passes_validation": True, "failed_gates": ""},
        {"candidate_id": "champion_current_formula", "passes_validation": True, "failed_gates": ""},
    ]

    selected = select_best_validated_formula(candidate_rows, gate_rows)

    assert selected["candidate_id"] == "validated_second"


def test_v3_best_validated_selection_prefers_oos_strength_over_full_sample_score():
    from research.regime_training import select_best_validated_formula

    candidate_rows = [
        {"candidate_id": "full_sample_leader", "profit_score": 80.0, "calmar": 1.2},
        {"candidate_id": "oos_leader", "profit_score": 70.0, "calmar": 1.0},
        {"candidate_id": "champion_current_formula", "profit_score": 50.0, "calmar": 0.5},
    ]
    gate_rows = [
        {"candidate_id": "full_sample_leader", "passes_validation": True, "failed_gates": ""},
        {"candidate_id": "oos_leader", "passes_validation": True, "failed_gates": ""},
        {"candidate_id": "champion_current_formula", "passes_validation": True, "failed_gates": ""},
    ]
    validation_rows = [
        {"candidate_id": "full_sample_leader", "oos_profit_score_delta_mean": 2.0, "oos_calmar_mean": 0.9},
        {"candidate_id": "oos_leader", "oos_profit_score_delta_mean": 8.0, "oos_calmar_mean": 1.4},
        {"candidate_id": "champion_current_formula", "oos_profit_score_delta_mean": 0.0, "oos_calmar_mean": 0.5},
    ]

    selected = select_best_validated_formula(candidate_rows, gate_rows, validation_rows)

    assert selected["candidate_id"] == "oos_leader"


def test_champion_policy_matches_validated_w0611_production_formula():
    from core.settings import get_section
    from cybernetics.regime_policy import PRODUCTION_REGIME_POLICY
    from research.regime_training import CHAMPION_POLICY

    detection = get_section("cybernetics.adaptive.detection")

    assert CHAMPION_POLICY.weights == PRODUCTION_REGIME_POLICY.normalized_weights
    assert CHAMPION_POLICY.bull_threshold == PRODUCTION_REGIME_POLICY.bull_threshold
    assert CHAMPION_POLICY.bear_threshold == PRODUCTION_REGIME_POLICY.bear_threshold
    assert CHAMPION_POLICY.trend_confirm == PRODUCTION_REGIME_POLICY.trend_confirm
    assert CHAMPION_POLICY.breadth_confirm == PRODUCTION_REGIME_POLICY.breadth_confirm
    assert CHAMPION_POLICY.bear_trend_breakdown == PRODUCTION_REGIME_POLICY.bear_trend_breakdown
    assert CHAMPION_POLICY.bear_breadth_breakdown == PRODUCTION_REGIME_POLICY.bear_breadth_breakdown
    assert CHAMPION_POLICY.min_dwell == PRODUCTION_REGIME_POLICY.min_dwell
    assert detection["regime_bull_threshold"] == PRODUCTION_REGIME_POLICY.bull_threshold
    assert detection["regime_bear_threshold"] == PRODUCTION_REGIME_POLICY.bear_threshold
    assert detection["regime_min_dwell"] == PRODUCTION_REGIME_POLICY.min_dwell


def test_profit_training_outputs_required_baselines_and_oos_decision():
    from research.regime_training import RegimePolicy, run_regime_profit_training

    panel = _asset_panel(periods=1800)
    features = _features(panel.index)
    policies = [
        RegimePolicy("trend_only_baseline", {"trend": 1.0}),
        RegimePolicy("trend_breadth_baseline", {"trend": 0.55, "breadth": 0.45}),
        RegimePolicy("challenger_cycle", {"trend": 0.35, "breadth": 0.35, "risk": 0.20, "volume": 0.10}),
    ]

    result = run_regime_profit_training(features, panel, policies=policies)

    strategies = {row["strategy"] for row in result["baseline_rows"]}
    assert {
        "buy_and_hold_equity",
        "fixed_80_20",
        "fixed_60_40",
        "fixed_40_60",
        "cash_only",
        "ma_20_60_timing",
        "ma_60_120_timing",
        "trend_only_regime",
        "trend_breadth_regime",
        "current_champion_formula",
        "best_challenger",
    }.issubset(strategies)
    assert result["walk_forward_rows"]
    assert all(row["train_end"] < row["validate_start"] for row in result["walk_forward_rows"])
    assert result["decision"] in {"keep_champion", "recommend_challenger_for_review"}
    assert result["best_unconstrained_id"]
    assert result["best_validated_id"]
    assert result["champion_gate_diagnostics"]["candidate_id"] == "champion_current_formula"
    assert result["candidate_gate_rows"]
    assert result["candidate_validation_summary_rows"]


def test_profit_report_writes_stable_schema_and_advisory_config(tmp_path):
    from research.regime_training import RegimePolicy, run_regime_profit_training, write_regime_profit_report

    panel = _asset_panel(periods=1300)
    features = _features(panel.index)
    result = run_regime_profit_training(
        features,
        panel,
        policies=[RegimePolicy("challenger_cycle", {"trend": 0.35, "breadth": 0.35, "risk": 0.20, "volume": 0.10})],
    )

    summary = write_regime_profit_report(tmp_path, result)

    required = {
        "summary.json",
        "profit_champion_vs_challenger.md",
        "tradable_asset_panel.parquet",
        "regime_feature_history.parquet",
        "regime_label_history.parquet",
        "candidate_profit_search.csv",
        "walk_forward_profit_results.csv",
        "baseline_comparison.csv",
        "regime_exposure_ab_test.csv",
        "regime_distribution.csv",
        "candidate_gate_diagnostics.csv",
        "candidate_validation_summary.csv",
        "event_study.csv",
        "recommended_profit_config.yaml",
        "run.log",
    }
    assert required.issubset(set(summary["report_files"]))
    assert json.loads((tmp_path / "summary.json").read_text())["decision"] == summary["decision"]
    assert "best_validated_id" in summary
    assert "champion_gate_diagnostics" in summary
    assert "apply: false" in (tmp_path / "recommended_profit_config.yaml").read_text()
