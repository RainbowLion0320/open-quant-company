import json


def test_strategy_evidence_report_contains_baselines_and_gates(tmp_path):
    from research.strategy_evaluation import (
        build_evidence_report,
        required_baselines,
        write_strategy_evidence_report,
    )

    report = build_evidence_report(
        strategy="trend_following",
        status="candidate",
        metrics={"cagr": 0.12, "sharpe": 0.8, "max_drawdown": -0.18, "turnover": 2.5, "trades": 36},
        oos={"months": 18, "start": "2024-01-01", "end": "2025-06-30"},
        regime_breakdown={"bull": {"return": 0.15}},
        data_readiness={"status": "blocked", "blockers": ["missing_score_panel"]},
    )
    path = write_strategy_evidence_report(report, output_dir=tmp_path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    baselines = required_baselines()

    assert set(saved["baselines"]) == set(baselines)
    assert "buy_and_hold" in saved["baselines"]
    assert "current_champion" in saved["baselines"]
    assert saved["strategy"] == "trend_following"
    assert saved["status"] == "candidate"
    assert saved["cost_model"]["commission"] > 0
    assert set(saved["regime_breakdown"]) == {"bull", "sideways", "bear"}
    assert saved["missing_evidence"] == ["ic", "icir"]
    assert saved["alpha_evidence"]["status"] == "missing"
    assert saved["data_readiness"]["blockers"] == ["missing_score_panel"]
    assert "missing_evidence:ic" in saved["promotion_decision"]["failed_rules"]
    assert saved["promotion_decision"]["target_status"] == "paper"
    assert not saved["promotion_decision"]["passed"]


def test_strategy_evidence_distinguishes_missing_ic_from_zero_ic():
    from research.strategy_evaluation import build_evidence_report

    missing = build_evidence_report(
        strategy="alpha",
        status="candidate",
        metrics={"cagr": 0.1, "sharpe": 0.8, "max_drawdown": -0.1, "turnover": 1.0, "trades": 100},
        oos={"months": 36},
    )
    measured_zero = build_evidence_report(
        strategy="alpha",
        status="candidate",
        metrics={
            "cagr": 0.1,
            "sharpe": 0.8,
            "max_drawdown": -0.1,
            "turnover": 1.0,
            "trades": 100,
            "ic": 0.0,
            "icir": 0.0,
        },
        oos={"months": 36},
    )

    assert missing["missing_evidence"] == ["ic", "icir"]
    assert "ic" not in missing["metrics"]
    assert "icir" not in missing["metrics"]
    assert measured_zero["missing_evidence"] == []
    assert measured_zero["metrics"]["ic"] == 0.0
    assert measured_zero["metrics"]["icir"] == 0.0


def test_backtest_evidence_includes_measured_alpha_evidence_from_score_panel(tmp_path, monkeypatch):
    import pandas as pd

    from research.strategy_evaluation import write_backtest_evidence

    monkeypatch.setattr(
        "research.strategy_competition.risk_free_series_for_index",
        lambda index: pd.Series(0.02, index=index),
    )
    idx = pd.bdate_range("2023-01-02", periods=820)
    score_rows = []
    for dt in pd.bdate_range("2024-01-02", periods=40):
        score_rows.extend(
            [
                {
                    "as_of_date": dt.date().isoformat(),
                    "symbol": "AAA",
                    "strategy": "alpha",
                    "score": 90.0,
                    "rank": 1,
                    "selected": True,
                    "forward_return_20d": 0.06,
                    "data_quality": "ok",
                },
                {
                    "as_of_date": dt.date().isoformat(),
                    "symbol": "BBB",
                    "strategy": "alpha",
                    "score": 10.0,
                    "rank": 2,
                    "selected": False,
                    "forward_return_20d": -0.03,
                    "data_quality": "ok",
                },
            ]
        )
    result = {
        "daily_returns": pd.Series(0.001, index=idx),
        "bench_returns": pd.Series(0.0001, index=idx),
        "trade_log": [(dt, "BUY", "AAA", 100, 10.0) for dt in idx[::20]],
        "commission": 0.00025,
        "slippage": 0.001,
        "score_panel": pd.DataFrame(score_rows),
    }

    path = write_backtest_evidence("alpha", "candidate", result, start="2023-01-02", end="2026-02-20", output_dir=tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["alpha_evidence"]["status"] == "measured"
    assert saved["alpha_evidence"]["ic"] > 0.9
    assert saved["metrics"]["ic"] > 0.9
    assert saved["backtest_evidence"]["score_panel_rows"] == len(score_rows)
