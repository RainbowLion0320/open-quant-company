"""
PipelineBacktest — daily backtest loop driven by the pipeline stages.

Uses the same Alpha→Portfolio→Risk→Execution stages that paper trading uses.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

import numpy as np
import pandas as pd

from pipeline.types import PipelineContext
from pipeline.alpha import AlphaModel
from pipeline.portfolio import PortfolioConstructor, EqualWeightConstructor
from pipeline.risk import RiskAdjuster
from pipeline.execution import ExecutionRouter, ExecutionConfig
from pipeline.scheduler import RebalanceScheduler, RebalanceConfig


class PipelineBacktest:
    """Run a daily backtest using pipeline stages for alpha, portfolio, risk, and execution."""

    def __init__(
        self,
        alpha: AlphaModel,
        portfolio: PortfolioConstructor | None = None,
        risk: RiskAdjuster | None = None,
        execution: ExecutionRouter | None = None,
        scheduler: RebalanceScheduler | None = None,
        cash: float = 1_000_000,
        commission_rate: float = 0.00081,
    ):
        self.alpha = alpha
        self.portfolio = portfolio or EqualWeightConstructor()
        self.risk = risk or RiskAdjuster()
        self.execution = execution or ExecutionRouter(ExecutionConfig(commission_rate=commission_rate))
        self.scheduler = scheduler or RebalanceScheduler()
        self.initial_cash = cash

    def run(
        self,
        prices: pd.DataFrame,
        bench_close: pd.Series,
        universe: list[str] | None = None,
        monthly_regimes: dict[str, str] | None = None,
    ) -> dict:
        """Run the backtest day by day and return the standard result dict."""
        if universe is None:
            universe = list(prices.columns)
        else:
            universe = [symbol for symbol in universe if symbol in prices.columns]
        price_history = prices.ffill()
        price_history.attrs = {}
        try:
            from backtest.candidate_alpha import transfer_price_panels

            transfer_price_panels(prices, price_history)
        except Exception:
            pass

        holdings: dict[str, int] = {}
        cost_basis: dict[str, float] = {}
        cash = self.initial_cash

        trade_log: list[tuple] = []
        daily_values: list[tuple] = []
        total_days = len(prices)

        for day_idx in range(total_days):
            dt = prices.index[day_idx]
            current_prices_raw = price_history.iloc[day_idx].reindex(universe)

            # Current prices as dict
            current_prices = {
                str(sym): float(val)
                for sym, val in current_prices_raw.dropna().items()
                if float(val) > 0
            }

            # Regime
            regime = "sideways"
            if monthly_regimes:
                regime = monthly_regimes.get(dt.strftime("%Y-%m"), "sideways")

            # Holdings check — prune zero positions
            holdings = {s: v for s, v in holdings.items() if v > 0}

            # Rebalance decision
            should_rebal = self.scheduler.should_rebalance(
                dt.date() if hasattr(dt, "date") else dt,
                regime,
                holdings,
                current_prices,
                strategy_trigger=lambda d, r, h: self.alpha.rebalance_trigger(d, r, h),
            )

            if should_rebal and total_days >= 200 and day_idx % (total_days // 5) == 0:
                print(f"  [{self.alpha.name}] 调仓 @ {dt.date()} regime={regime}  "
                      f"holdings={len(holdings)} cash={cash:,.0f}", flush=True)

            if should_rebal:
                # Build PipelineContext
                ctx = PipelineContext(
                    date=dt.date() if hasattr(dt, "date") else dt,
                    universe=universe,
                    prices=current_prices,
                    price_history=price_history,
                    regime=regime,
                    cash=cash,
                    holdings=dict(holdings),
                    cost_basis=dict(cost_basis),
                )

                # Stage 1: Alpha
                ctx.signals = self.alpha.generate_alpha(universe, price_history, day_idx, regime)

                # Stage 2: Portfolio
                ctx.targets = self.portfolio.construct(ctx.signals, ctx)
                self.scheduler.record_target(ctx.targets)

                # Stage 3: Risk
                ctx.adjusted_targets = self.risk.adjust(ctx.targets, ctx)

                # Stage 4: Execution
                ctx.intents = self.execution.targets_to_intents(ctx.adjusted_targets, ctx)
                fills = self.execution.execute(ctx.intents)  # backtest mode (no broker)

                # Apply fills
                for f in fills:
                    if f.status != "filled" or f.filled_shares <= 0:
                        continue
                    price = f.fill_price
                    shares = f.filled_shares

                    if f.side == "sell":
                        cash += (shares * price) - f.commission
                        if f.symbol in holdings:
                            holdings[f.symbol] -= shares
                            if holdings[f.symbol] <= 0:
                                holdings.pop(f.symbol, None)
                                cost_basis.pop(f.symbol, None)
                        trade_log.append((dt, "SELL", f.symbol, shares, price))

                    else:  # buy
                        cost = shares * price + f.commission
                        if cost <= cash:
                            cash -= cost
                            prev_shares = holdings.get(f.symbol, 0)
                            prev_cost = cost_basis.get(f.symbol, 0) * prev_shares
                            holdings[f.symbol] = prev_shares + shares
                            cost_basis[f.symbol] = (prev_cost + cost) / holdings[f.symbol] if holdings[f.symbol] > 0 else price
                            trade_log.append((dt, "BUY", f.symbol, shares, price))

            # Daily NAV
            mv = sum(
                holdings.get(sym, 0) * current_prices.get(sym, 0)
                for sym in set(list(holdings.keys()) + list(current_prices.keys()))
                if sym in current_prices
            )
            daily_values.append((dt, cash + mv))

        self.execution.end_of_day()

        # Build result
        vdf = pd.DataFrame(daily_values, columns=["date", "value"]).set_index("date")
        daily_returns = vdf["value"].pct_change().dropna()
        bench_returns = bench_close.pct_change().dropna()

        aligned = pd.concat([daily_returns, bench_returns], axis=1, join="inner").dropna()
        from backtest.analytics import RiskAnalytics
        report = RiskAnalytics.compute(aligned.iloc[:, 0], aligned.iloc[:, 1])

        return {
            "daily_returns": daily_returns,
            "bench_returns": bench_returns,
            "trade_log": trade_log,
            "final_holdings": dict(holdings),
            "total_return": report.total_return,
            "bench_return": (bench_close.iloc[-1] / bench_close.iloc[0] - 1) if len(bench_close) > 0 else 0,
            "sharpe": report.sharpe,
            "max_drawdown": report.max_drawdown,
            "win_rate": report.win_rate,
            "trade_count": len(trade_log),
            "commission": self.execution.config.commission_rate,
            "slippage": 0.001,
        }

    @staticmethod
    def _safe_price(series: pd.Series, idx: int) -> float | None:
        """Get the last valid price at or before idx."""
        try:
            vals = series.iloc[:idx + 1].dropna()
            if len(vals):
                return float(vals.iloc[-1])
        except Exception:
            pass
        return None
