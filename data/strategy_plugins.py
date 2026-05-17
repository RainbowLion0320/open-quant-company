"""Unified strategy runtime registry.

This module is the single dispatch point used by CLI scans and Web jobs.
Strategy metadata still lives in ``config/settings.yaml`` via ``data.registry``;
the runtime here resolves each strategy's configured runner and persists its
outputs in the canonical Parquet signal store.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Callable, Iterable

from data.registry import get_enabled_strategies, get_strategy, list_strategy_names
from data.results_db import (
    get_buffett_meta,
    list_strategies as list_saved_strategies,
    save_buffett_results,
    save_strategy_signals,
)


DEFAULT_RUNNERS = {
    "buffett": "scripts.compute_signals:compute_buffett",
    "multifactor": "scripts.compute_signals:compute_multifactor",
    "cybernetic": "scripts.compute_signals:compute_cybernetic",
    "ml_lgbm": "signals.ml_signals:compute_ml_signals",
}


@dataclass(frozen=True)
class StrategyPlugin:
    """Runtime contract for a registered strategy."""

    name: str
    label: str
    runner: str
    signal_name: str

    def load_runner(self) -> Callable[..., list[dict]]:
        module_name, _, attr = self.runner.partition(":")
        if not module_name or not attr:
            raise ValueError(f"Invalid runner for strategy {self.name}: {self.runner}")
        module = import_module(module_name)
        fn = getattr(module, attr)
        if not callable(fn):
            raise TypeError(f"Runner is not callable: {self.runner}")
        return fn

    def compute(self, limit: int = 0) -> list[dict]:
        return self.load_runner()(limit=limit)

    def to_signal_rows(self, results: list[dict]) -> list[dict]:
        if self.name != "buffett":
            return results

        rows = []
        for row in results:
            verdict = str(row.get("verdict", ""))
            passed = "通过" in verdict or "✅" in verdict
            rows.append(
                {
                    "symbol": row["symbol"],
                    "name": row.get("name", row["symbol"]),
                    "industry": row.get("industry", ""),
                    "score": row.get("score", 0),
                    "signal": "buy" if passed else "hold",
                    "detail": {
                        "verdict": verdict,
                        "safe_margin": row.get("safety_margin", 0),
                        "roe": row.get("roe", 0),
                    },
                }
            )
        return rows

    def save(self, results: list[dict]) -> None:
        if self.name == "buffett":
            save_buffett_results(results)
        save_strategy_signals(self.signal_name, self.to_signal_rows(results))


def get_strategy_plugin(name: str) -> StrategyPlugin | None:
    item = get_strategy(name)
    if not item:
        return None
    runner = item.get("runner") or DEFAULT_RUNNERS.get(name, "")
    return StrategyPlugin(
        name=name,
        label=item.get("label", name),
        runner=runner,
        signal_name=item.get("signal_name", name),
    )


def iter_strategy_plugins(selected: str = "all") -> Iterable[StrategyPlugin]:
    valid = set(list_strategy_names()) | {"all"}
    if selected not in valid:
        raise ValueError(f"Invalid strategy: {selected}. Choose from: {', '.join(sorted(valid))}")

    for item in get_enabled_strategies():
        name = item["name"]
        if selected not in ("all", name):
            continue
        plugin = get_strategy_plugin(name)
        if plugin:
            yield plugin


def run_strategy_plugin(plugin: StrategyPlugin, limit: int = 0) -> list[dict]:
    results = plugin.compute(limit=limit)
    plugin.save(results)
    if plugin.name == "buffett":
        meta = get_buffett_meta()
        print(f"  Saved: {meta.get('total', 0)} stocks, {meta.get('passed', 0)} passed")
    return results


def run_registered_strategies(
    selected: str = "all",
    limit: int = 0,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[dict]:
    plugins = list(iter_strategy_plugins(selected))
    if not plugins:
        raise ValueError(f"No enabled strategy plugin found for: {selected}")
    total = max(len(plugins), 1)
    for idx, plugin in enumerate(plugins, 1):
        if progress_callback:
            progress_callback(idx - 1, total, f"{plugin.label} running")
        print(f"\n── {plugin.label} ──")
        run_strategy_plugin(plugin, limit=limit)
        if progress_callback:
            progress_callback(idx, total, f"{plugin.label} done")
    return list_saved_strategies()
