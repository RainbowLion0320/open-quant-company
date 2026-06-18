"""
多策略对比回测 — 逐日引擎，策略自主调仓
产物: var/artifacts/backtests/backtest_<strategy>.pkl + backtest_comparison.pkl
"""

from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
for key in list(os.environ.keys()):
    if key.lower() in ("http_proxy", "https_proxy", "all_proxy"):
        del os.environ[key]
os.environ["no_proxy"] = "*"

import pandas as pd

from backtest.candidate_alpha import (
    CandidateStrategyAlphaModel,
    candidate_backtest_strategy_names,
    candidate_max_positions,
    is_candidate_backtest_strategy,
    register_price_panels,
)
from backtest.regime_replay import build_production_regime_map
from backtest.strategy_scorers import (
    BASE_STRATEGY_SCORERS,
    buffett_scorer,
    cybernetic_scorer,
    ml_lgbm_scorer,
    multifactor_scorer,
    settings,
)
from data.ingestion.fetcher import get_index_daily
from data.market.symbols import CIRCLE_STOCKS
from data.storage.datahub import get_datahub
from research.strategy_evaluation import write_backtest_evidence
from backtest.data_readiness import strategy_data_readiness

HUB = get_datahub()
BACKTEST_ARTIFACT_DIR = HUB.artifact_dir("backtests")
BACKTEST_CACHE_DIR = HUB.cache_root / "backtest"
BACKTEST_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _settings() -> dict:
    return settings()


def load_prices(pool, start, end):
    """加载回测价格矩阵。"""
    from core.settings import get_section
    from data.market.price_service import get_stock_price_matrix
    from data.market.price_types import PriceUseCase

    min_bars = int((get_section("backtest", {}) or {}).get("min_bars", 200))
    prices, panel_frames = get_stock_price_matrix(
        pool,
        use_case=PriceUseCase.BACKTEST,
        start=start,
        end=end,
        min_bars=min_bars,
        cache_dir=BACKTEST_CACHE_DIR,
    )
    if prices.empty:
        return None
    register_price_panels(prices, panel_frames)
    prices.attrs = {}
    print(f"  价格矩阵: {len(prices.columns)}/{len(pool)} 有效 (mode=qfq)")
    return prices


def backtest_strategy_names() -> list[str]:
    """Return registered strategy names with a concrete backtest adapter."""
    names = set(BASE_STRATEGY_SCORERS)
    names.update(candidate_backtest_strategy_names())
    return sorted(names)


def _current_champion_name(results: dict[str, dict], strategy_items: dict[str, dict]) -> str | None:
    """Select the current production peer used by evidence reports as champion baseline."""
    production = [
        name
        for name, item in strategy_items.items()
        if item.get("status") == "production" and name in results
    ]
    if "multifactor" in production:
        return "multifactor"
    if not production:
        return None
    return max(production, key=lambda name: float(results[name].get("sharpe", 0.0) or 0.0))


def _strategy_alpha_model(name: str, label: str, scorer_fn, alpha_min_score: int):
    from pipeline.alpha import StrategyAlphaAdapter

    if is_candidate_backtest_strategy(name):
        return CandidateStrategyAlphaModel(name=name, label=label)
    if name == "ml_lgbm":
        from backtest.strategies.ml_strategy import MLFeatureStoreAlphaModel

        return MLFeatureStoreAlphaModel(label=label, min_score=alpha_min_score)
    return StrategyAlphaAdapter(
        name=name,
        label=name,
        scorer=scorer_fn,
        min_score=alpha_min_score,
        rebalance_trigger=_strategy_trigger(name),
    )


def _strategy_trigger(name: str):
    return {
        "buffett": (
            lambda date, regime, holdings:
            date.month in (4, 5)
            and getattr(run_pipeline_backtest, "_last_buffett_year", 0) != date.year
            and not setattr(run_pipeline_backtest, "_last_buffett_year", date.year)
        ),
    }.get(name)


def run_pipeline_backtest(
    name,
    pool,
    prices,
    bench_close,
    scorer_fn,
    start,
    end,
    cash=1_000_000,
    monthly_regimes=None,
    label=None,
):
    """Run backtest via the pipeline stages shared with paper trading."""
    from core.settings import get_section
    from backtest.pipeline_runner import PipelineBacktest
    from pipeline.portfolio import EqualWeightConstructor
    from pipeline.scheduler import RebalanceConfig, RebalanceScheduler

    if monthly_regimes is None:
        monthly_regimes = build_production_regime_map(bench_close)

    backtest_cfg = get_section("backtest", {}) or {}
    rebalance_cfg = backtest_cfg.get("rebalance", {}) or {}
    max_position_cfg = backtest_cfg.get("max_positions", {}) or {}
    drift = float(rebalance_cfg.get("drift_threshold", 0.75))
    overlap = float(rebalance_cfg.get("overlap_threshold", 0.50))
    alpha_min = int(backtest_cfg.get("alpha_min_score", 30))

    scheduler_configs = {
        "buffett": RebalanceConfig(schedule="drift", force_months=[4, 5], max_idle_days=365),
        "multifactor": RebalanceConfig(schedule="monthly", drift_threshold=drift, min_overlap_pct=overlap),
        "cybernetic": RebalanceConfig(schedule="regime_change", drift_threshold=drift),
        "ml_lgbm": RebalanceConfig(schedule="monthly", drift_threshold=drift),
        "trend_following": RebalanceConfig(schedule="monthly", drift_threshold=drift, min_overlap_pct=overlap),
        "donchian_breakout": RebalanceConfig(schedule="monthly", drift_threshold=drift, min_overlap_pct=overlap),
        "rps_relative_strength": RebalanceConfig(schedule="monthly", drift_threshold=drift, min_overlap_pct=overlap),
        "sector_rotation": RebalanceConfig(schedule="monthly", drift_threshold=drift, min_overlap_pct=overlap),
        "quality_value": RebalanceConfig(schedule="monthly", drift_threshold=drift, min_overlap_pct=overlap),
        "low_vol_defensive": RebalanceConfig(schedule="monthly", drift_threshold=drift, min_overlap_pct=overlap),
        "volume_confirmation": RebalanceConfig(schedule="monthly", drift_threshold=drift, min_overlap_pct=overlap),
        "regime_gated": RebalanceConfig(schedule="regime_change", drift_threshold=drift, min_overlap_pct=overlap),
    }
    max_positions = {"buffett": 8, "multifactor": 10, "cybernetic": 5, "ml_lgbm": 8}
    for candidate_name in candidate_backtest_strategy_names():
        max_positions[candidate_name] = candidate_max_positions(candidate_name)
    max_positions = {key: int(max_position_cfg.get(key, value)) for key, value in max_positions.items()}

    runner = PipelineBacktest(
        alpha=_strategy_alpha_model(name, label or name, scorer_fn, alpha_min),
        portfolio=EqualWeightConstructor(max_positions=max_positions.get(name, 8)),
        scheduler=RebalanceScheduler(scheduler_configs.get(name, RebalanceConfig())),
        cash=cash,
    )
    return runner.run(prices, bench_close, universe=pool, monthly_regimes=monthly_regimes)


def run_strategy_comparison(strategy: str = "") -> dict:
    bt_cfg = _settings().get("backtest", {})
    pool_size = bt_cfg.get("pool_size", 0)
    pool = list(CIRCLE_STOCKS)
    if pool_size > 0:
        pool = pool[:pool_size]
    start = bt_cfg.get("start_date", "2015-01-01")
    end = bt_cfg.get("end_date", "2026-05-10")
    runner_label = "pipeline"
    print(f"策略对比回测 [{runner_label}]: {len(pool)} stocks, {start} ~ {end}")

    prices = load_prices(pool, start, end)
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])
    bench = bench.set_index("date").sort_index()
    bench_close = bench["close"].loc[pd.Timestamp(start):pd.Timestamp(end)]
    monthly_regimes = build_production_regime_map(bench_close)
    print(f"基准: {bench_close.iloc[0]:.0f} -> {bench_close.iloc[-1]:.0f} ({((bench_close.iloc[-1]/bench_close.iloc[0]-1)*100):+.2f}%)")

    from data.strategy.catalog import get_enabled_strategies

    scorer_map = dict(BASE_STRATEGY_SCORERS)
    for candidate_name in candidate_backtest_strategy_names():
        scorer_map[candidate_name] = None

    enabled_strategies = get_enabled_strategies()
    if strategy:
        enabled_strategies = [item for item in enabled_strategies if item["name"] == strategy]
        if not enabled_strategies:
            raise SystemExit(f"Unknown or disabled strategy: {strategy}")
    strategy_items = {item["name"]: dict(item) for item in enabled_strategies}

    results = {}
    for item in enabled_strategies:
        name = item["name"]
        scorer = scorer_map.get(name)
        if name not in scorer_map:
            print(f"  跳过 {name}: 无对应评分器")
            continue
        if name in {"buffett", "multifactor"} and scorer is not None:
            scorer._pool = list(prices.columns)

        schedule_desc = {
            "buffett": "年报季+漂移",
            "multifactor": "月度+漂移",
            "cybernetic": "regime+漂移",
            "ml_lgbm": "月度+漂移",
        }
        print(f"\n  {item['label']} (调仓: {schedule_desc.get(name, 'default')})")
        results[name] = run_pipeline_backtest(
            name,
            pool,
            prices,
            bench_close,
            scorer,
            start,
            end,
            monthly_regimes=monthly_regimes,
            cash=float(bt_cfg.get("initial_cash", 1_000_000)),
            label=item.get("label", name),
        )
        results[name]["data_readiness"] = strategy_data_readiness(item, as_of=end)
        with open(BACKTEST_ARTIFACT_DIR / f"backtest_{name}.pkl", "wb") as f:
            pickle.dump(results[name], f)

    current_champion = _current_champion_name(results, strategy_items)
    for item in enabled_strategies:
        name = item["name"]
        if name not in results:
            continue
        write_backtest_evidence(
            name,
            item.get("status", "candidate"),
            results[name],
            start=start,
            end=end,
            price_matrix=prices,
            peer_results=results,
            current_champion=current_champion,
        )

    comparison = {
        "strategies": {
            name: {
                "total_return": result["total_return"],
                "sharpe": result["sharpe"],
                "max_drawdown": result["max_drawdown"],
                "win_rate": result["win_rate"],
                "trade_count": result["trade_count"],
            }
            for name, result in results.items()
        },
        "bench_return": bench_close.iloc[-1] / bench_close.iloc[0] - 1,
        "start": start,
        "end": end,
        "runner": runner_label,
    }
    with open(BACKTEST_ARTIFACT_DIR / "backtest_comparison.pkl", "wb") as f:
        pickle.dump(comparison, f)

    print(f"\n{'='*60}")
    print(f"策略对比 [{runner_label}]:")
    print(f"基准: {comparison['bench_return']*100:+.2f}%")
    for name, result in comparison["strategies"].items():
        print(
            f"  {name}: {result['total_return']*100:+.2f}%  "
            f"Sharpe {result['sharpe']:.2f}  MaxDD {result['max_drawdown']*100:.1f}%  "
            f"Win {result['win_rate']*100:.0f}%  {result['trade_count']}笔"
        )
    return comparison


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", action="store_true", help="Use pipeline-based backtest runner")
    parser.add_argument("--strategy", default="", help="Run one registered strategy by name")
    args = parser.parse_args()
    run_strategy_comparison(strategy=args.strategy)
