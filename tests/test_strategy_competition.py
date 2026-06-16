from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd


def _result(daily_return: float, bench_return: float, *, days: int = 820, trades: int = 120) -> dict:
    idx = pd.bdate_range("2023-01-02", periods=days)
    trade_log = []
    if trades > 0:
        for dt in idx[:: max(days // trades, 1)][:trades]:
            trade_log.append((dt, "BUY", "000001", 100, 10.0))
    return {
        "daily_returns": pd.Series(daily_return, index=idx),
        "bench_returns": pd.Series(bench_return, index=idx),
        "trade_log": trade_log,
        "commission": 0.00025,
        "slippage": 0.001,
    }


def _score_panel(days: int = 80) -> pd.DataFrame:
    rows = []
    for dt in pd.bdate_range("2024-01-02", periods=days):
        rows.extend(
            [
                {
                    "as_of_date": dt.date().isoformat(),
                    "symbol": "AAA",
                    "strategy": "new_alpha",
                    "score": 90.0,
                    "rank": 1,
                    "selected": True,
                    "forward_return_20d": 0.08,
                    "data_quality": "ok",
                },
                {
                    "as_of_date": dt.date().isoformat(),
                    "symbol": "BBB",
                    "strategy": "new_alpha",
                    "score": 10.0,
                    "rank": 2,
                    "selected": False,
                    "forward_return_20d": -0.02,
                    "data_quality": "ok",
                },
            ]
        )
    return pd.DataFrame(rows)


def test_strategy_competition_recommends_from_oos_not_previous_status(monkeypatch, tmp_path):
    from research.strategy_competition import build_strategy_competition_report

    monkeypatch.setattr(
        "research.strategy_competition.get_enabled_strategies",
        lambda: [
            {"name": "old_prod", "label": "Old production", "status": "production", "layer": "candidate_alpha"},
            {"name": "new_alpha", "label": "New alpha", "status": "candidate", "layer": "candidate_alpha"},
        ],
    )
    monkeypatch.setattr(
        "research.strategy_competition.risk_free_series_for_index",
        lambda index: pd.Series(0.02, index=index),
    )
    with (tmp_path / "backtest_old_prod.pkl").open("wb") as f:
        pickle.dump(_result(-0.0002, 0.0001), f)
    new_alpha = _result(0.0010, 0.0001)
    new_alpha["score_panel"] = _score_panel()
    new_alpha["data_readiness"] = {"status": "ok", "blockers": []}
    with (tmp_path / "backtest_new_alpha.pkl").open("wb") as f:
        pickle.dump(new_alpha, f)

    report = build_strategy_competition_report(backtest_dir=tmp_path)
    rows = {row["strategy"]: row for row in report["rankings"]}

    assert rows["new_alpha"]["rank"] == 1
    assert rows["new_alpha"]["recommended_status"] == "production"
    assert rows["new_alpha"]["alpha_evidence"]["status"] == "measured"
    assert rows["new_alpha"]["alpha_evidence"]["ic"] > 0.9
    assert rows["new_alpha"]["alpha_evidence"]["icir"] >= 0.35
    assert "missing_ic" not in rows["new_alpha"]["warnings"]
    assert "missing_icir" not in rows["new_alpha"]["warnings"]
    assert rows["old_prod"]["recommended_status"] == "candidate"
    assert rows["old_prod"]["competition_valid"] is False
    assert "missing_score_panel" in rows["old_prod"]["data_quality"]["blockers"]
    assert "positive_oos_return" in rows["old_prod"]["paper_blockers"]


def test_strategy_competition_report_writes_latest(monkeypatch, tmp_path):
    from research.strategy_competition import write_strategy_competition_report

    monkeypatch.setattr(
        "research.strategy_competition.get_enabled_strategies",
        lambda: [{"name": "alpha", "label": "Alpha", "status": "candidate", "layer": "candidate_alpha"}],
    )
    monkeypatch.setattr(
        "research.strategy_competition.risk_free_series_for_index",
        lambda index: pd.Series(0.02, index=index),
    )
    result = _result(0.0010, 0.0001)
    result["score_panel"] = _score_panel().assign(strategy="alpha")
    result["data_readiness"] = {"status": "ok", "blockers": []}
    with (tmp_path / "backtest_alpha.pkl").open("wb") as f:
        pickle.dump(result, f)

    report, path = write_strategy_competition_report(backtest_dir=tmp_path, output_dir=tmp_path / "out")

    assert path.exists()
    assert (tmp_path / "out" / "strategy_competition_latest.json").exists()
    assert report["summary"]["strategy_count"] == 1
    assert report["summary"]["recommended_counts"]["production"] == 1
    assert report["summary"]["invalid_count"] == 0


def test_ml_strategy_with_insufficient_feature_store_is_invalid(monkeypatch, tmp_path):
    from research.strategy_competition import build_strategy_competition_report

    monkeypatch.setattr(
        "research.strategy_competition.get_enabled_strategies",
        lambda: [{"name": "ml_lgbm", "label": "ML", "status": "paper", "layer": "auxiliary_alpha"}],
    )
    monkeypatch.setattr(
        "research.strategy_competition.risk_free_series_for_index",
        lambda index: pd.Series(0.02, index=index),
    )
    monkeypatch.setattr(
        "data.features.feature_store.feature_store_coverage",
        lambda **_: {
            "daily_file_count": 1,
            "ignored_file_count": 90,
            "sampled_file_count": 1,
            "row_count": 1,
            "symbol_count": 1,
            "start": "2026-05-08",
            "end": "2026-05-08",
            "truncated": False,
            "read_errors": [],
        },
    )
    with (tmp_path / "backtest_ml_lgbm.pkl").open("wb") as f:
        pickle.dump(_result(0.0, 0.0001, trades=0), f)

    report = build_strategy_competition_report(backtest_dir=tmp_path)
    row = report["rankings"][0]

    assert row["competition_valid"] is False
    assert row["rank_score"] == -999999.0
    assert row["recommended_status"] == "candidate"
    assert "feature_store_date_coverage" in row["data_quality"]["blockers"]
    assert "feature_store_symbol_coverage" in row["data_quality"]["blockers"]
    assert "ignored_noncanonical_feature_files" in row["warnings"]
    assert report["summary"]["invalid_count"] == 1


def test_strategy_data_readiness_uses_backtest_as_of_coverage(monkeypatch):
    from backtest import data_readiness

    rows = pd.DataFrame(
        [
            {
                "registry_key": "sector_sw_daily",
                "freshness_status": "stale",
                "freshness_date": "2026-06-09",
            },
            {
                "registry_key": "sector_membership",
                "freshness_status": "unknown",
                "freshness_date": "",
            },
            {
                "registry_key": "ohlcv_daily",
                "freshness_status": "fresh",
                "freshness_date": "2026-06-12",
            },
            {
                "registry_key": "adj_factor",
                "freshness_status": "fresh",
                "freshness_date": "2026-06-12",
            },
        ]
    )
    monkeypatch.setattr(data_readiness, "_HEALTH_ROWS_CACHE", rows)

    item = {"data_requirements": ["stock_daily", "sector"]}
    covered = data_readiness.strategy_data_readiness(item, as_of="2026-05-08")
    uncovered = data_readiness.strategy_data_readiness(item, as_of="2026-06-12")

    assert covered["status"] == "ok"
    assert covered["statuses"]["sector_sw_daily"] == "available_as_of"
    assert covered["blockers"] == []
    assert uncovered["status"] == "blocked"
    assert "stale_data:sector_sw_daily" in uncovered["blockers"]
