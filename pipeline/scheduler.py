"""
RebalanceScheduler — decide when to rebalance based on config and strategy hooks.

Unified scheduling logic shared by backtest and paper trading.
Strategies can override via rebalance_trigger(date, regime, holdings) → bool.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional


@dataclass
class RebalanceConfig:
    """Schedule configuration for a strategy or portfolio."""

    schedule: str = "monthly"  # "monthly" | "weekly" | "regime_change" | "drift" | "daily"
    drift_threshold: float = 0.50  # position drift beyond which rebalance is forced
    min_overlap_pct: float = 0.50  # holdings/target overlap below which rebalance is forced
    force_months: list[int] = field(default_factory=list)  # e.g. [4, 5] for annual report season
    max_idle_days: int = 28  # force rebalance if no rebalance for this many days


class RebalanceScheduler:
    """Determines whether to rebalance based on config, regime, and strategy hooks."""

    def __init__(self, config: RebalanceConfig | None = None):
        self.config = config or RebalanceConfig()
        self._last_rebalance_date: date | None = None
        self._last_regime: str | None = None
        self._last_target_symbols: set[str] = set()

    def should_rebalance(
        self,
        dt: date,
        regime: str,
        holdings: dict[str, int],
        current_prices: dict[str, float],
        strategy_trigger: Optional[Callable[[date, str, dict[str, int]], bool]] = None,
    ) -> bool:
        cfg = self.config

        # Strategy override
        if strategy_trigger and strategy_trigger(dt, regime, holdings):
            self._record(dt, regime)
            return True

        # First run
        if self._last_rebalance_date is None:
            self._record(dt, regime)
            return True

        # Forced months (e.g. buffett's April/May)
        if dt.month in cfg.force_months:
            if self._last_rebalance_date.month != dt.month or self._last_rebalance_date.year != dt.year:
                self._record(dt, regime)
                return True

        # Regime change
        if cfg.schedule == "regime_change" or self._last_regime != regime:
            if self._last_regime is not None and self._last_regime != regime:
                self._record(dt, regime)
                return True

        # Monthly
        if cfg.schedule == "monthly" and dt.month != self._last_rebalance_date.month:
            self._record(dt, regime)
            return True

        # Weekly
        if cfg.schedule == "weekly":
            if (dt - self._last_rebalance_date).days >= 7:
                self._record(dt, regime)
                return True

        # Daily
        if cfg.schedule == "daily":
            self._record(dt, regime)
            return True

        # Drift check
        if cfg.schedule == "drift" and holdings:
            drift = self._compute_drift(holdings, current_prices)
            if drift > cfg.drift_threshold:
                self._record(dt, regime)
                return True

        # Max idle guard
        if (dt - self._last_rebalance_date).days >= cfg.max_idle_days:
            self._record(dt, regime)
            return True

        # Holdings changed significantly vs last target
        if cfg.schedule in ("drift", "monthly") and holdings and self._last_target_symbols:
            current_symbols = set(holdings.keys())
            if current_symbols:
                overlap = len(current_symbols & self._last_target_symbols) / len(current_symbols)
                if overlap < cfg.min_overlap_pct:
                    self._record(dt, regime)
                    return True

        return False

    def record_target(self, targets) -> None:
        """Remember the last computed target set for overlap comparison."""
        if targets:
            self._last_target_symbols = {t.symbol for t in targets if t.target_weight > 0}

    def _record(self, dt: date, regime: str) -> None:
        self._last_rebalance_date = dt
        self._last_regime = regime

    def _compute_drift(self, holdings: dict[str, int], prices: dict[str, float]) -> float:
        if len(holdings) < 3:
            return 0.0
        total = 0.0
        values: dict[str, float] = {}
        for sym, shares in holdings.items():
            p = prices.get(sym, 0)
            if p <= 0:
                continue
            v = shares * p
            values[sym] = v
            total += v
        if total <= 0:
            return 0.0
        n = len(values)
        target_w = 1.0 / n
        max_drift = 0.0
        for v in values.values():
            actual = v / total
            drift = abs(actual - target_w) / target_w
            max_drift = max(max_drift, drift)
        return max_drift
