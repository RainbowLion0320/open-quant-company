from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd


def _result(daily_return: float, bench_return: float, *, days: int = 820, trades: int = 120) -> dict:
    idx = pd.bdate_range("2023-01-02", periods=days)
    trade_log = []
    for dt in idx[:: max(days // trades, 1)][:trades]:
        trade_log.append((dt, "BUY", "000001", 100, 10.0))
    return {
        "daily_returns": pd.Series(daily_return, index=idx),
        "bench_returns": pd.Series(bench_return, index=idx),
        "trade_log": trade_log,
        "commission": 0.00025,
        "slippage": 0.001,
    }


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
    with (tmp_path / "backtest_new_alpha.pkl").open("wb") as f:
        pickle.dump(_result(0.0010, 0.0001), f)

    report = build_strategy_competition_report(backtest_dir=tmp_path)
    rows = {row["strategy"]: row for row in report["rankings"]}

    assert rows["new_alpha"]["rank"] == 1
    assert rows["new_alpha"]["recommended_status"] == "paper"
    assert rows["new_alpha"]["production_blockers"] == ["ic", "icir"]
    assert rows["old_prod"]["recommended_status"] == "candidate"
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
    with (tmp_path / "backtest_alpha.pkl").open("wb") as f:
        pickle.dump(_result(0.0010, 0.0001), f)

    report, path = write_strategy_competition_report(backtest_dir=tmp_path, output_dir=tmp_path / "out")

    assert path.exists()
    assert (tmp_path / "out" / "strategy_competition_latest.json").exists()
    assert report["summary"]["strategy_count"] == 1
    assert report["summary"]["recommended_counts"]["paper"] == 1
