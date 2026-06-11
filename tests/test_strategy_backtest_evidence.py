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
