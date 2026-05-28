"""Shared momentum-selection helpers for research tournament scripts."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import pandas as pd

from broker.exchange import OrderSide
from signals.technical import momentum_score

ScoreFn = Callable[[pd.Series, Any], float]


def price_at(prices: pd.DataFrame, symbol: str, dt: Any) -> float | None:
    if symbol not in prices.columns:
        return None
    try:
        price = prices[symbol].get(dt, None)
        if price is None or pd.isna(price) or float(price) <= 0:
            return None
        return float(price)
    except Exception:
        return None


def select_top_momentum(
    prices: pd.DataFrame,
    dt: Any,
    n_pos: int,
    *,
    score_fn: ScoreFn | None = None,
) -> list[tuple[str, float]]:
    scorer = score_fn or momentum_score
    scores: dict[str, float] = {}
    for symbol in list(prices.columns):
        score = float(scorer(prices[symbol], dt))
        if score > 0:
            scores[symbol] = score
    return sorted(scores.items(), key=lambda item: -item[1])[:n_pos]


def liquidate_positions(
    holdings: dict[str, int],
    cash: float,
    price_books: Iterable[tuple[pd.DataFrame, Any]],
    dt: Any,
) -> tuple[float, dict[str, int]]:
    next_holdings = dict(holdings)
    for symbol in list(next_holdings):
        price = None
        exchange = None
        for prices, candidate_exchange in price_books:
            price = price_at(prices, symbol, dt)
            if price is not None:
                exchange = candidate_exchange
                break
        if price is None or exchange is None:
            continue
        shares = next_holdings.pop(symbol)
        cash += shares * price - exchange.calc_cost(price, shares, OrderSide.SELL)
    return cash, next_holdings


def buy_equal_weight_selection(
    holdings: dict[str, int],
    cash: float,
    prices: pd.DataFrame,
    dt: Any,
    exchange: Any,
    selection: list[tuple[str, float]],
    budget: float,
    *,
    cash_buffer: float = 0.99,
    lot_size: int = 100,
) -> tuple[float, dict[str, int], int]:
    if not selection or cash <= 0 or budget <= 0:
        return cash, holdings, 0

    next_holdings = dict(holdings)
    budget_per_symbol = min(cash, budget) / len(selection) * cash_buffer
    trades = 0
    for symbol, _score in selection:
        price = price_at(prices, symbol, dt)
        if price is None:
            continue
        shares = int(budget_per_symbol / price / lot_size) * lot_size
        if shares < lot_size:
            continue
        cost = exchange.calc_cost(price, shares, OrderSide.BUY)
        total_cost = shares * price + cost
        if total_cost > cash:
            continue
        cash -= total_cost
        next_holdings[symbol] = next_holdings.get(symbol, 0) + shares
        trades += 1
    return cash, next_holdings, trades


def portfolio_value(
    cash: float,
    holdings: dict[str, int],
    price_books: Iterable[pd.DataFrame],
    dt: Any,
) -> float:
    value = float(cash)
    for symbol, shares in holdings.items():
        for prices in price_books:
            price = price_at(prices, symbol, dt)
            if price is not None:
                value += shares * price
                break
    return value


def run_monthly_rebalance_strategy(
    prices: pd.DataFrame,
    dates: Iterable[Any],
    exchange: Any,
    *,
    n_pos: int,
    cash: float,
    score_fn: ScoreFn | None = None,
) -> tuple[float, int]:
    holdings: dict[str, int] = {}
    values: list[float] = []
    trades = 0
    timeline = list(dates)

    for day_idx, dt in enumerate(timeline):
        if day_idx == 0 or pd.Timestamp(dt).month != pd.Timestamp(timeline[day_idx - 1]).month:
            selection = select_top_momentum(prices, dt, n_pos, score_fn=score_fn)
            cash, holdings = liquidate_positions(holdings, cash, [(prices, exchange)], dt)
            if selection and cash > 0:
                cash, holdings, new_trades = buy_equal_weight_selection(
                    holdings,
                    cash,
                    prices,
                    dt,
                    exchange,
                    selection,
                    cash,
                )
                trades += new_trades
        values.append(portfolio_value(cash, holdings, [prices], dt))

    if not values or values[0] <= 0:
        return 0.0, trades
    return (values[-1] / values[0] - 1.0) * 100.0, trades
