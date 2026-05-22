"""
RiskAdjuster — apply risk rules to portfolio targets.

Delegates to the existing broker.risk.RiskManager for individual rule checks
and adjusts/removes targets that violate limits.

This is Stage 3 of the pipeline: PortfolioTarget → (adjusted) PortfolioTarget.
"""

from __future__ import annotations

from typing import Optional
import copy

import numpy as np

from pipeline.types import PortfolioTarget, PipelineContext
from broker.risk import RiskManager


class RiskAdjuster:
    """Apply risk limits to portfolio targets, shrinking or removing violations."""

    def __init__(self, risk_manager: Optional[RiskManager] = None):
        self._rm = risk_manager or RiskManager()

    def adjust(
        self,
        targets: list[PortfolioTarget],
        ctx: PipelineContext,
    ) -> list[PortfolioTarget]:
        """Return adjusted targets after risk checks."""
        if not targets:
            return []

        total_equity = ctx.cash + sum(
            ctx.holdings.get(s, 0) * ctx.prices.get(s, 0) for s in ctx.holdings
        )
        current_mv = sum(
            ctx.holdings.get(s, 0) * ctx.prices.get(s, 0) for s in ctx.holdings
        )
        peak_equity = max(ctx.cash, total_equity)

        portfolio = {
            "total_equity": total_equity,
            "total_exposure": current_mv,
            "peak_equity": peak_equity,
            "positions": {
                s: {"market_value": ctx.holdings.get(s, 0) * ctx.prices.get(s, 0)}
                for s in ctx.holdings if s in ctx.prices
            },
        }

        adjusted: list[PortfolioTarget] = []

        for t in targets:
            if t.delta_shares == 0:
                adjusted.append(t)
                continue

            amount = abs(t.delta_shares) * ctx.prices.get(t.symbol, 0)
            passed, results = self._rm.check_order(t.symbol, amount, portfolio)

            if passed:
                adjusted.append(t)
                continue

            # Try shrinking: reduce to half and re-check
            shrunk = copy.copy(t)
            shrunk.delta_shares = shrunk.delta_shares // 2
            shrunk.target_shares = t.current_shares + shrunk.delta_shares
            shrunk_amount = abs(shrunk.delta_shares) * ctx.prices.get(t.symbol, 0)

            passed2, _ = self._rm.check_order(t.symbol, shrunk_amount, portfolio)
            if passed2 and shrunk.delta_shares != 0:
                shrunk.reason += f" [risk-shrunk: {'; '.join(r.reason for r in results if not r.passed)}]"
                adjusted.append(shrunk)
            else:
                # Remove this target — record as zero-delta
                rejected = copy.copy(t)
                rejected.delta_shares = 0
                rejected.target_shares = t.current_shares
                rejected.reason = f"RISK REJECTED: {'; '.join(r.reason for r in results if not r.passed)}"
                adjusted.append(rejected)

        return adjusted
