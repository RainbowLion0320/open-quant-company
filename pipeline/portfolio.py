"""
PortfolioConstructor — turn alpha signals into target positions.

Two implementations:
  EqualWeightConstructor    — Top-N, each gets 1/N of allocated capital
  InverseVolatilityConstructor — lower vol → higher weight within Top-N
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.types import AlphaSignal, PortfolioTarget, PipelineContext


class PortfolioConstructor(ABC):
    """Abstract portfolio construction stage."""

    @abstractmethod
    def construct(
        self,
        signals: list[AlphaSignal],
        ctx: PipelineContext,
    ) -> list[PortfolioTarget]:
        """Build target positions from alpha signals and current state."""
        ...


class EqualWeightConstructor(PortfolioConstructor):
    """Top-N stocks get equal allocation from deployable capital."""

    def __init__(
        self,
        max_positions: int = 8,
        position_pct: float = 0.30,
        lot_size: int = 100,
    ):
        self.max_positions = max_positions
        self.position_pct = position_pct  # fraction of cash to deploy
        self.lot_size = lot_size

    def construct(self, signals, ctx):
        if not signals:
            return []

        top = signals[:self.max_positions]
        n = len(top)
        weight = 1.0 / n

        total_equity = ctx.cash + sum(
            ctx.holdings.get(s, 0) * ctx.prices.get(s, 0)
            for s in ctx.holdings
        )
        deployable = ctx.cash * self.position_pct
        per_symbol = deployable / n if n > 0 else 0

        current_symbols = set(ctx.holdings.keys())
        target_symbols = {s.symbol for s in top}

        targets: list[PortfolioTarget] = []

        for signal in top:
            sym = signal.symbol
            price = ctx.prices.get(sym, 0)
            if price <= 0:
                continue

            target_shares = max(0, int(per_symbol / price // self.lot_size) * self.lot_size)
            current_vol = ctx.holdings.get(sym, 0)
            current_w = (current_vol * price) / total_equity if total_equity > 0 else 0

            targets.append(PortfolioTarget(
                symbol=sym,
                strategy=signal.strategy,
                target_weight=round(weight, 4),
                target_shares=target_shares,
                current_weight=round(current_w, 4),
                current_shares=current_vol,
                delta_shares=target_shares - current_vol,
                reason=f"Top-{n} equal-weight {weight:.1%}",
            ))

        # Sell signals for positions no longer in target
        for sym in current_symbols - target_symbols:
            if sym not in ctx.prices:
                continue
            cur_vol = ctx.holdings.get(sym, 0)
            if cur_vol <= 0:
                continue
            cur_w = (cur_vol * ctx.prices[sym]) / total_equity if total_equity > 0 else 0
            targets.append(PortfolioTarget(
                symbol=sym,
                strategy="",
                target_weight=0,
                target_shares=0,
                current_weight=round(cur_w, 4),
                current_shares=cur_vol,
                delta_shares=-cur_vol,  # sell all
                reason="Removed from Top-N",
            ))

        return targets


class InverseVolatilityConstructor(PortfolioConstructor):
    """Top-N stocks weighted by inverse volatility — lower vol gets higher allocation."""

    def __init__(
        self,
        max_positions: int = 8,
        position_pct: float = 0.30,
        vol_window: int = 63,
        min_weight: float = 0.03,
        lot_size: int = 100,
    ):
        self.max_positions = max_positions
        self.position_pct = position_pct
        self.vol_window = vol_window
        self.min_weight = min_weight
        self.lot_size = lot_size

    def construct(self, signals, ctx):
        if not signals:
            return []

        top = signals[:self.max_positions]
        price_history = ctx.price_history

        # Compute volatilities
        vols: dict[str, float] = {}
        for signal in top:
            sym = signal.symbol
            if price_history is not None and sym in price_history.columns:
                vols[sym] = self._compute_vol(price_history[sym])
            else:
                vols[sym] = 0.30  # default 30% annual vol

        # Inverse-vol weights
        inv_vols = {s: 1.0 / max(v, 0.01) for s, v in vols.items()}
        total_inv = sum(inv_vols.values())
        raw_weights = {s: iv / total_inv for s, iv in inv_vols.items()} if total_inv > 0 else {}

        # Floor at min_weight and renormalize
        for s in raw_weights:
            raw_weights[s] = max(raw_weights[s], self.min_weight)

        total_w = sum(raw_weights.values())
        weights = {s: w / total_w for s, w in raw_weights.items()} if total_w > 0 else {}

        total_equity = ctx.cash + sum(
            ctx.holdings.get(s, 0) * ctx.prices.get(s, 0)
            for s in ctx.holdings
        )
        deployable = ctx.cash * self.position_pct
        current_symbols = set(ctx.holdings.keys())
        target_symbols = {s.symbol for s in top}

        targets: list[PortfolioTarget] = []

        for signal in top:
            sym = signal.symbol
            price = ctx.prices.get(sym, 0)
            if price <= 0:
                continue

            w = weights.get(sym, 0)
            target_val = deployable * w
            target_shares = max(0, int(target_val / price // self.lot_size) * self.lot_size)
            current_vol = ctx.holdings.get(sym, 0)
            current_w = (current_vol * price) / total_equity if total_equity > 0 else 0

            targets.append(PortfolioTarget(
                symbol=sym,
                strategy=signal.strategy,
                target_weight=round(w, 4),
                target_shares=target_shares,
                current_weight=round(current_w, 4),
                current_shares=current_vol,
                delta_shares=target_shares - current_vol,
                reason=f"InvVol w={w:.1%} vol={vols.get(sym,0):.1%}",
            ))

        for sym in current_symbols - target_symbols:
            if sym not in ctx.prices:
                continue
            cur_vol = ctx.holdings.get(sym, 0)
            if cur_vol <= 0:
                continue
            cur_w = (cur_vol * ctx.prices[sym]) / total_equity if total_equity > 0 else 0
            targets.append(PortfolioTarget(
                symbol=sym,
                strategy="",
                target_weight=0,
                target_shares=0,
                current_weight=round(cur_w, 4),
                current_shares=cur_vol,
                delta_shares=-cur_vol,
                reason="Removed from Top-N",
            ))

        return targets

    def _compute_vol(self, series: pd.Series) -> float:
        """Annualized volatility from daily close returns."""
        clean = series.dropna()
        if len(clean) < self.vol_window // 2:
            return 0.30
        window = clean.tail(self.vol_window)
        rets = window.pct_change().dropna()
        if len(rets) < 10:
            return 0.30
        return float(rets.std() * np.sqrt(252))


class ConstrainedPortfolioConstructor(PortfolioConstructor):
    """Top-N constructor with single-name and sector exposure caps."""

    def __init__(
        self,
        max_positions: int = 8,
        position_pct: float = 0.80,
        max_single_weight: float = 0.15,
        max_sector_weight: float = 0.30,
        sector_map: dict[str, str] | None = None,
        lot_size: int = 100,
    ):
        self.max_positions = max_positions
        self.position_pct = position_pct
        self.max_single_weight = max_single_weight
        self.max_sector_weight = max_sector_weight
        self.sector_map = sector_map or {}
        self.lot_size = lot_size

    def construct(self, signals, ctx):
        if not signals:
            return []

        total_equity = ctx.cash + sum(
            ctx.holdings.get(sym, 0) * ctx.prices.get(sym, 0)
            for sym in ctx.holdings
        )
        if total_equity <= 0:
            return []

        base_weight = min(self.max_single_weight, self.position_pct / max(self.max_positions, 1))
        selected = []
        sector_weights: dict[str, float] = {}
        planned_weight = 0.0

        for signal in signals:
            if signal.direction != "buy":
                continue
            if len(selected) >= self.max_positions:
                break
            price = ctx.prices.get(signal.symbol, 0)
            if price <= 0:
                continue
            sector = self.sector_map.get(signal.symbol) or f"unknown:{signal.symbol}"
            if planned_weight + base_weight > self.position_pct + 1e-12:
                break
            if sector_weights.get(sector, 0.0) + base_weight > self.max_sector_weight + 1e-12:
                continue
            selected.append((signal, sector, base_weight))
            sector_weights[sector] = sector_weights.get(sector, 0.0) + base_weight
            planned_weight += base_weight

        target_symbols = {signal.symbol for signal, _sector, _weight in selected}
        current_symbols = set(ctx.holdings.keys())
        targets: list[PortfolioTarget] = []

        for signal, sector, weight in selected:
            price = ctx.prices.get(signal.symbol, 0)
            target_value = total_equity * weight
            target_shares = max(0, int(target_value / price // self.lot_size) * self.lot_size)
            current_vol = ctx.holdings.get(signal.symbol, 0)
            current_w = (current_vol * price) / total_equity if total_equity > 0 else 0
            display_sector = sector.split(":", 1)[0] if sector.startswith("unknown:") else sector
            targets.append(PortfolioTarget(
                symbol=signal.symbol,
                strategy=signal.strategy,
                target_weight=round(weight, 4),
                target_shares=target_shares,
                current_weight=round(current_w, 4),
                current_shares=current_vol,
                delta_shares=target_shares - current_vol,
                reason=f"Constrained Top-{self.max_positions}; sector={display_sector}; cap={self.max_sector_weight:.0%}",
            ))

        for sym in current_symbols - target_symbols:
            price = ctx.prices.get(sym, 0)
            cur_vol = ctx.holdings.get(sym, 0)
            if price <= 0 or cur_vol <= 0:
                continue
            cur_w = (cur_vol * price) / total_equity
            targets.append(PortfolioTarget(
                symbol=sym,
                strategy="",
                target_weight=0.0,
                target_shares=0,
                current_weight=round(cur_w, 4),
                current_shares=cur_vol,
                delta_shares=-cur_vol,
                reason="Removed by constrained portfolio target",
            ))

        return targets
