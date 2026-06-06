"""Candidate strategy score functions for pipeline backtests."""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from backtest.candidate_alpha_features import (
    annualized_volatility_frame,
    asof_row,
    avg_recent_positive,
    drawdown_control_frame,
    history,
    panel_history,
    pct_return_frame,
    quality_financial_inputs,
    rank_values,
    score_rows,
    valuation_panels,
    volume_ratio_frame,
)
from data.market.symbols import SYMBOL_INDUSTRY
from signals.candidates.common import bounded_score, percentile_score, safe_float
from signals.candidates.params import candidate_strategy_params


def score_candidate_strategy(name: str, universe: list[str], prices: pd.DataFrame, date_idx: int, regime: str) -> dict[str, dict]:
    if name == "regime_gated":
        return _regime_gated(universe, prices, date_idx, regime)
    scorer = _SCORERS.get(name)
    if scorer is None:
        return {}
    return scorer(universe, prices, date_idx)


def _trend_following(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("trend_following")
    weights = params["score_weights"]
    score_values = params["trend_score_values"]
    close = history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    latest = close.iloc[-1]
    short_ma = close.tail(int(params["short_ma_window"])).mean()
    medium_ma = close.tail(int(params["medium_ma_window"])).mean()
    long_ma = close.tail(int(params["long_ma_window"])).mean()
    trend = pd.Series(0.0, index=close.columns)
    trend = trend.mask(latest > long_ma, float(score_values["price_above_long"]))
    trend = trend.mask(latest > medium_ma, float(score_values["price_above_medium"]))
    trend = trend.mask(short_ma > medium_ma, float(score_values["medium"]))
    trend = trend.mask((latest > short_ma) & (short_ma > medium_ma), float(score_values["strong"]))
    above_long = pd.Series(0.0, index=close.columns).mask(latest > long_ma, 100.0)
    momentum = pct_return_frame(close, int(params["momentum_window"]))
    momentum_rank = pd.Series(rank_values(momentum.dropna().to_dict()))
    scores = (
        trend * float(weights["trend"])
        + above_long * float(weights["above_long_ma"])
        + momentum_rank.reindex(close.columns).fillna(0.0) * float(weights["momentum"])
    )
    return score_rows(scores, {"trend": trend, "momentum_rank": momentum_rank})


def _donchian_breakout(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("donchian_breakout")
    weights = params["score_weights"]
    close = history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    high = panel_history(prices, "high", date_idx)
    volume = panel_history(prices, "volume", date_idx)
    high_window = high.tail(int(params["breakout_window"])).max().replace(0, pd.NA)
    proximity = (close.iloc[-1] / high_window * 100.0).clip(0.0, 100.0)
    volume_ratio = volume_ratio_frame(volume, int(params["volume_window"]))
    volatility = annualized_volatility_frame(close, int(params["volatility_window"]))
    volume_rank = pd.Series(rank_values(volume_ratio.dropna().to_dict()))
    inverse_vol_rank = pd.Series(rank_values((-volatility).dropna().to_dict()))
    scores = (
        proximity * float(weights["breakout_proximity"])
        + volume_rank.reindex(close.columns).fillna(0.0) * float(weights["volume"])
        + inverse_vol_rank.reindex(close.columns).fillna(0.0) * float(weights["inverse_volatility"])
    )
    return score_rows(scores, {"breakout_proximity": proximity})


def _rps_relative_strength(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("rps_relative_strength")
    weights = params["score_weights"]
    close = history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    short_rps = pct_return_frame(close, int(params["short_return_window"]), skip_recent=int(params["skip_recent_window"]))
    long_rps = pct_return_frame(close, int(params["long_return_window"]), skip_recent=int(params["skip_recent_window"]))
    trend_ma = close.tail(int(params["trend_ma_window"])).mean()
    trend_filter = pd.Series(0.0, index=close.columns).mask(close.iloc[-1] > trend_ma, 100.0)
    short_rank = pd.Series(rank_values(short_rps.dropna().to_dict()))
    long_rank = pd.Series(rank_values(long_rps.dropna().to_dict()))
    scores = (
        short_rank.reindex(close.columns).fillna(0.0) * float(weights["short_rps"])
        + long_rank.reindex(close.columns).fillna(0.0) * float(weights["long_rps"])
        + trend_filter * float(weights["trend_filter"])
    )
    return score_rows(scores, {"short_rps_rank": short_rank, "long_rps_rank": long_rank})


def _sector_rotation(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("sector_rotation")
    weights = params["score_weights"]
    close = history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    short_return = pct_return_frame(close, int(params["short_return_window"]))
    long_return = pct_return_frame(close, int(params["long_return_window"]))
    metrics = [
        {
            "symbol": symbol,
            "industry": SYMBOL_INDUSTRY.get(symbol, ""),
            "short_return": safe_float(short_return.get(symbol, 0.0)),
            "long_return": safe_float(long_return.get(symbol, 0.0)),
        }
        for symbol in close.columns
    ]
    frame = pd.DataFrame(metrics)
    industry_short = frame.groupby("industry")["short_return"].median()
    industry_long = frame.groupby("industry")["long_return"].median()
    industry_short_rank = percentile_score(industry_short)
    industry_long_rank = percentile_score(industry_long)
    stock_rank: dict[str, float] = {}
    for _, group in frame.groupby("industry"):
        stock_rank.update(percentile_score(group.set_index("symbol")["short_return"]))
    return {
        metric["symbol"]: {
            "score": bounded_score(
                industry_short_rank.get(metric["industry"], 0.0) * float(weights["industry_short"])
                + industry_long_rank.get(metric["industry"], 0.0) * float(weights["industry_long"])
                + stock_rank.get(metric["symbol"], 0.0) * float(weights["stock_inside_industry"])
            ),
            "detail": {"industry": metric["industry"], "stock_rank": stock_rank.get(metric["symbol"], 0.0)},
        }
        for metric in metrics
    }


def _quality_value(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("quality_value")
    weights = params["score_weights"]
    recent_period_count = int(params["recent_period_count"])
    try:
        as_of = pd.Timestamp(prices.index[date_idx])
    except Exception:
        as_of = pd.Timestamp(datetime.now().date())

    fin_inputs = quality_financial_inputs(as_of.year, universe)
    valuation = valuation_panels(universe)
    pe_ttm = asof_row(valuation.get("pe_ttm", pd.DataFrame()), as_of).reindex(universe)
    pb = asof_row(valuation.get("pb", pd.DataFrame()), as_of).reindex(universe)

    metrics = []
    for symbol in universe:
        inputs = fin_inputs.get(symbol, {})
        metrics.append({
            "symbol": symbol,
            "roe": avg_recent_positive(inputs.get("roe_history", []), recent_period_count),
            "gross_margin": avg_recent_positive(inputs.get("gross_margin_history", []), recent_period_count),
            "pe_ttm": safe_float(pe_ttm.get(symbol, 0.0)),
            "pb": safe_float(pb.get(symbol, 0.0)),
        })
    roe_rank = rank_values({metric["symbol"]: metric["roe"] for metric in metrics})
    gm_rank = rank_values({metric["symbol"]: metric["gross_margin"] for metric in metrics})
    pe_rank = rank_values({metric["symbol"]: -metric["pe_ttm"] for metric in metrics if metric["pe_ttm"] > 0})
    pb_rank = rank_values({metric["symbol"]: -metric["pb"] for metric in metrics if metric["pb"] > 0})
    return {
        metric["symbol"]: {
            "score": bounded_score(
                roe_rank.get(metric["symbol"], 0.0) * float(weights["roe"])
                + gm_rank.get(metric["symbol"], 0.0) * float(weights["gross_margin"])
                + pe_rank.get(metric["symbol"], 0.0) * float(weights["inverse_pe"])
                + pb_rank.get(metric["symbol"], 0.0) * float(weights["inverse_pb"])
            ),
            "detail": {"roe_rank": roe_rank.get(metric["symbol"], 0.0), "gross_margin_rank": gm_rank.get(metric["symbol"], 0.0)},
        }
        for metric in metrics
    }


def _low_vol_defensive(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("low_vol_defensive")
    weights = params["score_weights"]
    close = history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    amount = panel_history(prices, "amount", date_idx)
    volatility = annualized_volatility_frame(close, int(params["volatility_window"]))
    drawdown = drawdown_control_frame(close, int(params["drawdown_window"]))
    trend = (
        float(params["trend_score_base"])
        + pct_return_frame(close, int(params["trend_window"])) * float(params["trend_score_scale"])
    ).clip(0.0, 100.0)
    liquidity = amount.tail(int(params["liquidity_window"])).mean()
    inverse_vol_rank = pd.Series(rank_values((-volatility).dropna().to_dict()))
    liquidity_rank = pd.Series(rank_values(liquidity.dropna().to_dict()))
    scores = (
        inverse_vol_rank.reindex(close.columns).fillna(0.0) * float(weights["inverse_volatility"])
        + drawdown * float(weights["drawdown_control"])
        + trend * float(weights["trend"])
        + liquidity_rank.reindex(close.columns).fillna(0.0) * float(weights["liquidity"])
    )
    return score_rows(scores, {"inverse_vol_rank": inverse_vol_rank, "drawdown_control": drawdown})


def _volume_confirmation(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("volume_confirmation")
    weights = params["score_weights"]
    close = history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    volume = panel_history(prices, "volume", date_idx)
    turnover = panel_history(prices, "turnover", date_idx)
    amount = panel_history(prices, "amount", date_idx)
    volume_ratio = volume_ratio_frame(volume, int(params["volume_window"]))
    momentum = pct_return_frame(close, int(params["momentum_window"]))
    flow_window = int(params["flow_window"])
    flow_proxy = turnover.tail(flow_window).mean()
    flow_proxy = flow_proxy.where(flow_proxy > 0, amount.tail(flow_window).mean())
    volume_rank = pd.Series(rank_values(volume_ratio.dropna().to_dict()))
    momentum_rank = pd.Series(rank_values(momentum.dropna().to_dict()))
    flow_rank = pd.Series(rank_values(flow_proxy.dropna().to_dict()))
    scores = (
        volume_rank.reindex(close.columns).fillna(0.0) * float(weights["volume"])
        + momentum_rank.reindex(close.columns).fillna(0.0) * float(weights["momentum"])
        + flow_rank.reindex(close.columns).fillna(0.0) * float(weights["flow"])
    )
    return score_rows(scores, {"volume_rank": volume_rank, "momentum_rank": momentum_rank})


def _regime_gated(universe: list[str], prices: pd.DataFrame, date_idx: int, regime: str) -> dict[str, dict]:
    params = candidate_strategy_params("regime_gated")
    regime_weights = params["regime_weights"].get(regime, params["regime_weights"].get("sideways", {}))
    min_active_weight = float(params["min_active_weight"])
    merged_scores: dict[str, float] = {}
    merged_weights: dict[str, float] = {}
    for source_name, weight in regime_weights.items():
        weight = float(weight)
        if weight <= min_active_weight:
            continue
        for symbol, row in score_candidate_strategy(source_name, universe, prices, date_idx, regime).items():
            merged_scores[symbol] = merged_scores.get(symbol, 0.0) + float(row.get("score", 0.0)) * weight
            merged_weights[symbol] = merged_weights.get(symbol, 0.0) + weight
    return {
        symbol: {
            "score": bounded_score(score / max(merged_weights.get(symbol, 0.0), 1e-12)),
            "detail": {"regime": regime},
        }
        for symbol, score in merged_scores.items()
    }


_SCORERS = {
    "trend_following": _trend_following,
    "donchian_breakout": _donchian_breakout,
    "rps_relative_strength": _rps_relative_strength,
    "sector_rotation": _sector_rotation,
    "quality_value": _quality_value,
    "low_vol_defensive": _low_vol_defensive,
    "volume_confirmation": _volume_confirmation,
}
