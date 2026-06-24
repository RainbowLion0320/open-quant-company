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
from broker.exchange import AShareExchange, Exchange, default_multi_asset_exchange
from data.market.assets.contracts import instrument_key, split_instrument_key


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
        exchange: Exchange | None = None,
    ):
        self.alpha = alpha
        self.portfolio = portfolio or EqualWeightConstructor()
        self.risk = risk or RiskAdjuster()
        self.execution = execution or ExecutionRouter(
            ExecutionConfig(exchange=exchange or default_multi_asset_exchange(AShareExchange()))
        )
        self.scheduler = scheduler or RebalanceScheduler()
        self.initial_cash = cash

    def run(
        self,
        prices: pd.DataFrame,
        bench_close: pd.Series,
        universe: list[str] | None = None,
        asset_types: dict[str, str] | None = None,
        monthly_regimes: dict[str, str] | None = None,
    ) -> dict:
        """Run the backtest day by day and return the standard result dict."""
        if universe is None:
            universe = list(prices.columns)
        else:
            universe = [symbol for symbol in universe if symbol in prices.columns]
        asset_types = {str(k): str(v or "stock") for k, v in (asset_types or {}).items()}
        universe_assets = {symbol: asset_types.get(symbol, "stock") for symbol in universe}
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
        score_panel_rows: list[dict] = []
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
            for sym, asset_type in universe_assets.items():
                if sym in current_prices:
                    current_prices[instrument_key(asset_type, sym)] = current_prices[sym]

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
                visible_price_history = price_history.iloc[: day_idx + 1].copy()
                visible_price_history.attrs = dict(getattr(price_history, "attrs", {}) or {})
                visible_day_idx = len(visible_price_history) - 1
                # Build PipelineContext
                ctx = PipelineContext(
                    date=dt.date() if hasattr(dt, "date") else dt,
                    universe=universe,
                    universe_assets=universe_assets,
                    prices=current_prices,
                    price_history=visible_price_history,
                    regime=regime,
                    cash=cash,
                    holdings=dict(holdings),
                    cost_basis=dict(cost_basis),
                )

                # Stage 1: Alpha
                ctx.signals = self.alpha.generate_alpha(universe, visible_price_history, visible_day_idx, regime)
                score_panel_rows.extend(
                    self._score_panel_rows(
                        universe=universe,
                        visible_prices=visible_price_history,
                        full_prices=price_history,
                        full_idx=day_idx,
                        visible_idx=visible_day_idx,
                        regime=regime,
                        signals=ctx.signals,
                        universe_assets=universe_assets,
                    )
                )

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
                        key = f.key
                        if key in holdings:
                            holdings[key] -= shares
                            if holdings[key] <= 0:
                                holdings.pop(key, None)
                                cost_basis.pop(key, None)
                        trade_log.append((dt, "SELL", f.asset_type, f.symbol, shares, price))

                    else:  # buy
                        cost = shares * price + f.commission
                        if cost <= cash:
                            cash -= cost
                            key = f.key
                            prev_shares = holdings.get(key, 0)
                            prev_cost = cost_basis.get(key, 0) * prev_shares
                            holdings[key] = prev_shares + shares
                            cost_basis[key] = (prev_cost + cost) / holdings[key] if holdings[key] > 0 else price
                            trade_log.append((dt, "BUY", f.asset_type, f.symbol, shares, price))

            # Daily NAV
            mv = sum(
                quantity * current_prices.get(key, 0)
                for key, quantity in holdings.items()
                if key in current_prices
            )
            daily_values.append((dt, cash + mv))

        self.execution.end_of_day()

        # Build result
        vdf = pd.DataFrame(daily_values, columns=["date", "value"]).set_index("date")
        daily_returns = vdf["value"].pct_change().dropna()
        bench_returns = bench_close.pct_change().dropna()

        aligned = pd.concat([daily_returns, bench_returns], axis=1, join="inner").dropna()
        from backtest.analytics import RiskAnalytics
        from data.rates.risk_free_rates import risk_free_series_for_index

        risk_free_rates = risk_free_series_for_index(aligned.index)
        report = RiskAnalytics.compute(aligned.iloc[:, 0], aligned.iloc[:, 1], risk_free_rates=risk_free_rates)

        return {
            "daily_returns": daily_returns,
            "bench_returns": bench_returns,
            "trade_log": trade_log,
            "score_panel": pd.DataFrame(score_panel_rows),
            "alpha_diagnostics": self._alpha_diagnostics(),
            "final_holdings": dict(holdings),
            "final_holdings_by_asset": self._holdings_by_asset(holdings),
            "total_return": report.total_return,
            "bench_return": (bench_close.iloc[-1] / bench_close.iloc[0] - 1) if len(bench_close) > 0 else 0,
            "sharpe": report.sharpe,
            "max_drawdown": report.max_drawdown,
            "win_rate": report.win_rate,
            "trade_count": len(trade_log),
            "commission": float(getattr(getattr(self.execution, "exchange", None), "commission", 0.0) or 0.0),
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

    def _score_panel_rows(
        self,
        *,
        universe: list[str],
        visible_prices: pd.DataFrame,
        full_prices: pd.DataFrame,
        full_idx: int,
        visible_idx: int,
        regime: str,
        signals: list,
        universe_assets: dict[str, str] | None = None,
    ) -> list[dict]:
        raw_rows = self.alpha.generate_score_panel(universe, visible_prices, visible_idx, regime)
        if not raw_rows:
            raw_rows = [
                {
                    "symbol": signal.symbol,
                    "strategy": signal.strategy,
                    "score": signal.score,
                    "horizon_days": signal.horizon_days,
                    "timestamp": signal.timestamp,
                    "data_quality": "signal_only",
                }
                for signal in signals
            ]
        if not raw_rows:
            return []

        signal_symbols = {str(signal.symbol) for signal in signals}
        signal_asset_types = {str(signal.symbol): str(getattr(signal, "asset_type", "stock") or "stock") for signal in signals}
        dt = full_prices.index[full_idx]
        numeric_scores = pd.Series(
            {
                idx: pd.to_numeric(row.get("score"), errors="coerce")
                for idx, row in enumerate(raw_rows)
            },
            dtype="float64",
        )
        ranks = numeric_scores.rank(ascending=False, method="first")
        out: list[dict] = []
        for idx, row in enumerate(raw_rows):
            symbol = str(row.get("symbol", ""))
            if not symbol or symbol not in full_prices.columns:
                continue
            horizon = int(row.get("horizon_days") or 20)
            forward_return = self._forward_return(full_prices[symbol], full_idx, horizon)
            score_value = pd.to_numeric(row.get("score"), errors="coerce")
            out.append(
                {
                    "as_of_date": dt.date().isoformat() if hasattr(dt, "date") else str(dt),
                    "symbol": symbol,
                    "asset_type": signal_asset_types.get(symbol) or (universe_assets or {}).get(symbol, "stock"),
                    "strategy": row.get("strategy") or self.alpha.name,
                    "score": float(score_value) if pd.notna(score_value) else None,
                    "rank": int(ranks.loc[idx]) if pd.notna(ranks.loc[idx]) else None,
                    "selected": bool(symbol in signal_symbols),
                    "forward_return_20d": forward_return if horizon == 20 else None,
                    "forward_return": forward_return,
                    "horizon_days": horizon,
                    "feature_version": row.get("feature_version", ""),
                    "model_version": row.get("model_version", ""),
                    "data_quality": row.get("data_quality", "ok"),
                    "regime": regime,
                }
            )
        return out

    @staticmethod
    def _forward_return(series: pd.Series, idx: int, horizon: int) -> float | None:
        target_idx = idx + horizon
        if target_idx >= len(series):
            return None
        try:
            current = float(series.iloc[idx])
            future = float(series.iloc[target_idx])
        except Exception:
            return None
        if not np.isfinite(current) or not np.isfinite(future) or current <= 0:
            return None
        return float(future / current - 1.0)

    def _alpha_diagnostics(self) -> dict:
        errors = []
        if hasattr(self.alpha, "load_errors"):
            errors.extend(str(item) for item in getattr(self.alpha, "load_errors") or [])
        strategy = getattr(self.alpha, "strategy", None)
        if strategy is not None and hasattr(strategy, "load_errors"):
            errors.extend(str(item) for item in getattr(strategy, "load_errors") or [])
        return {
            "alpha_model": self.alpha.__class__.__name__,
            "strategy": getattr(self.alpha, "name", ""),
            "load_errors": sorted(dict.fromkeys(errors)),
        }

    @staticmethod
    def _holdings_by_asset(holdings: dict[str, int]) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for key, quantity in holdings.items():
            asset_type, symbol = split_instrument_key(key)
            out.setdefault(asset_type, {})[symbol] = int(quantity)
        return out
