"""Point-in-time AlphaModel adapters for candidate strategies."""

from __future__ import annotations

import hashlib
import pickle
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from core.settings import get_dotted, get_settings
from data.symbols import SYMBOL_INDUSTRY
from pipeline.alpha import AlphaModel
from pipeline.types import AlphaSignal
from signals.candidates.common import bounded_score, percentile_score, safe_float
from signals.candidates.params import CANDIDATE_STRATEGY_NAMES, candidate_strategy_params

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_PRICE_PANELS: dict[int, dict[str, pd.DataFrame]] = {}
_VALUATION_PANELS: dict[tuple[str, ...], dict[str, pd.DataFrame]] = {}
_QUALITY_FINANCIAL_CACHE: dict[tuple[int, tuple[str, ...]], dict[str, dict]] = {}


def register_price_panels(prices: pd.DataFrame, panels: dict[str, pd.DataFrame]) -> None:
    _PRICE_PANELS[id(prices)] = panels


def transfer_price_panels(source: pd.DataFrame, target: pd.DataFrame) -> None:
    panels = _PRICE_PANELS.get(id(source))
    if panels is not None:
        _PRICE_PANELS[id(target)] = panels


def candidate_backtest_strategy_names() -> tuple[str, ...]:
    return CANDIDATE_STRATEGY_NAMES


def is_candidate_backtest_strategy(name: str) -> bool:
    return name in CANDIDATE_STRATEGY_NAMES


def candidate_selection_config(name: str) -> dict[str, Any]:
    cfg = get_settings()
    global_cfg = cfg.get("signal_selection", {}) if isinstance(cfg, dict) else {}
    strategy_cfg = get_dotted(cfg, f"signal_selection.strategies.{name}", {}) or {}
    merged = {
        "min_score": global_cfg.get("min_score", 50),
        "top_pct": global_cfg.get("top_pct", 0.05),
        "min_buys": global_cfg.get("min_buys", 5),
        "max_buys": global_cfg.get("max_buys", 20),
    }
    if isinstance(strategy_cfg, Mapping):
        merged.update(strategy_cfg)
    return merged


def candidate_max_positions(name: str) -> int:
    return int(candidate_selection_config(name).get("max_buys", 20))


def candidate_min_score(name: str) -> float:
    return float(candidate_selection_config(name).get("min_score", 50))


def _history(prices: pd.DataFrame, date_idx: int) -> pd.DataFrame:
    history = prices.iloc[: date_idx + 1]
    history.attrs = {}
    return history


def _panel_history(prices: pd.DataFrame, key: str, date_idx: int) -> pd.DataFrame:
    panels = _PRICE_PANELS.get(id(prices), {})
    panel = panels.get(key) if isinstance(panels, dict) else None
    if isinstance(panel, pd.DataFrame) and not panel.empty:
        history = panel.iloc[: date_idx + 1]
        history.attrs = {}
        return history
    return _history(prices, date_idx)


def _close(frame: pd.DataFrame) -> pd.Series:
    if frame.empty or "close" not in frame.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame["close"], errors="coerce").dropna()


def _moving_average(close: pd.Series, window: int) -> float:
    if len(close) < window:
        return 0.0
    return safe_float(close.tail(window).mean())


def _pct_return(close: pd.Series, window: int, *, skip_recent: int = 0) -> float:
    if len(close) < window + skip_recent + 1:
        return 0.0
    end_idx = -1 - skip_recent if skip_recent else -1
    start_idx = end_idx - window
    base = safe_float(close.iloc[start_idx])
    latest = safe_float(close.iloc[end_idx])
    return latest / base - 1.0 if base else 0.0


def _annualized_volatility(close: pd.Series, window: int, default: float = 0.30) -> float:
    if len(close) < window + 1:
        return default
    returns = close.pct_change().dropna().tail(window)
    if returns.empty:
        return default
    return safe_float(returns.std() * (252 ** 0.5), default)


def _volume_ratio(frame: pd.DataFrame, window: int) -> float:
    if "volume" not in frame.columns or len(frame) < window + 1:
        return 1.0
    volume = pd.to_numeric(frame["volume"], errors="coerce").dropna()
    if len(volume) < window + 1:
        return 1.0
    base = safe_float(volume.iloc[-window - 1 : -1].mean(), 1.0)
    return safe_float(volume.iloc[-1], 0.0) / base if base else 1.0


def _drawdown_control_score(close: pd.Series, window: int) -> float:
    if len(close) < 2:
        return 0.0
    recent = close.tail(window)
    peak = recent.cummax()
    drawdown = (recent / peak - 1.0).min()
    return bounded_score(100.0 + safe_float(drawdown) * 250.0)


def _rank(values: dict[str, float]) -> dict[str, float]:
    return percentile_score(pd.Series(values)) if values else {}


def _pct_return_frame(close: pd.DataFrame, window: int, *, skip_recent: int = 0) -> pd.Series:
    if len(close) < window + skip_recent + 1:
        return pd.Series(dtype="float64")
    end_idx = -1 - skip_recent if skip_recent else -1
    start_idx = end_idx - window
    base = pd.to_numeric(close.iloc[start_idx], errors="coerce")
    latest = pd.to_numeric(close.iloc[end_idx], errors="coerce")
    return latest / base.replace(0, pd.NA) - 1.0


def _annualized_volatility_frame(close: pd.DataFrame, window: int, default: float = 0.30) -> pd.Series:
    if len(close) < window + 1:
        return pd.Series(default, index=close.columns, dtype="float64")
    returns = close.pct_change().tail(window)
    return returns.std().fillna(default) * (252 ** 0.5)


def _volume_ratio_frame(volume: pd.DataFrame, window: int) -> pd.Series:
    if len(volume) < window + 1:
        return pd.Series(1.0, index=volume.columns, dtype="float64")
    base = volume.iloc[-window - 1 : -1].mean().replace(0, pd.NA)
    return (volume.iloc[-1] / base).fillna(1.0)


def _drawdown_control_frame(close: pd.DataFrame, window: int) -> pd.Series:
    if len(close) < 2:
        return pd.Series(0.0, index=close.columns, dtype="float64")
    recent = close.tail(window)
    drawdown = (recent / recent.cummax() - 1.0).min()
    return (100.0 + drawdown.fillna(0.0) * 250.0).clip(0.0, 100.0)


def _score_rows(scores: pd.Series, detail: dict[str, pd.Series] | None = None) -> dict[str, dict]:
    detail = detail or {}
    rows: dict[str, dict] = {}
    for symbol, score in scores.dropna().items():
        rows[str(symbol)] = {
            "score": bounded_score(score),
            "detail": {
                key: safe_float(values.get(symbol, 0.0))
                for key, values in detail.items()
            },
        }
    return rows


def _avg_recent_positive(values: list[float], period_count: int) -> float:
    recent = [safe_float(v) for v in values[-period_count:] if safe_float(v) > 0]
    return sum(recent) / len(recent) if recent else 0.0


def _asof_row(frame: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="float64")
    idx = frame.index.searchsorted(as_of, side="right") - 1
    if idx < 0:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame.iloc[idx], errors="coerce")


def _quality_financial_inputs(year: int, universe: list[str]) -> dict[str, dict]:
    key = (int(year), tuple(universe))
    if key not in _QUALITY_FINANCIAL_CACHE:
        from backtest.buffett_real_scorer import build_pit_financial_inputs

        _QUALITY_FINANCIAL_CACHE[key] = build_pit_financial_inputs(
            year,
            universe,
            log_label="质量价值",
        )
    return _QUALITY_FINANCIAL_CACHE[key]


def _valuation_panels(universe: list[str]) -> dict[str, pd.DataFrame]:
    symbols = tuple(universe)
    if symbols in _VALUATION_PANELS:
        return _VALUATION_PANELS[symbols]

    from data.datahub import get_datahub

    hub = get_datahub()
    existing_paths = []
    latest_mtime = 0
    for symbol in symbols:
        path = hub.stock_valuation_path(symbol)
        if not path.exists():
            continue
        existing_paths.append((symbol, path))
        latest_mtime = max(latest_mtime, path.stat().st_mtime_ns)

    cache_seed = f"valuation|{len(symbols)}|{len(existing_paths)}|{latest_mtime}"
    cache_key = hashlib.md5(cache_seed.encode()).hexdigest()[:12]
    cache_path = DATA_DIR / f"backtest_valuation_matrix_{cache_key}.pkl"
    if cache_path.exists():
        with open(cache_path, "rb") as f:
            panels = pickle.load(f)
        _VALUATION_PANELS[symbols] = panels
        print(f"  估值矩阵缓存命中: {len(existing_paths)}/{len(symbols)} 有效")
        return panels

    values: dict[str, dict[str, pd.Series]] = {"pe_ttm": {}, "pb": {}}
    total = len(existing_paths)
    for i, (symbol, path) in enumerate(existing_paths):
        if (i + 1) % max(1, total // 10) == 0 or i == 0:
            print(f"  加载估值: {i+1}/{total}", end="\r", flush=True)
        try:
            df = hub.read_parquet(path)
            if df is None or df.empty or "trade_date" not in df.columns:
                continue
            dates = pd.to_datetime(df["trade_date"], errors="coerce")
            for column in values:
                if column not in df.columns:
                    continue
                series = pd.to_numeric(df[column], errors="coerce")
                series.index = dates
                series = series[~series.index.isna()].sort_index()
                series = series[~series.index.duplicated(keep="last")]
                if not series.empty:
                    values[column][symbol] = series.rename(symbol)
        except Exception:
            continue

    print(f"  加载估值: {sum(len(v) for v in values.values())//max(1, len(values))}/{total} 有效")
    panels = {
        column: pd.concat(series_map.values(), axis=1, keys=series_map.keys()).sort_index().ffill()
        if series_map else pd.DataFrame()
        for column, series_map in values.items()
    }
    with open(cache_path, "wb") as f:
        pickle.dump(panels, f)
    _VALUATION_PANELS[symbols] = panels
    return panels


def _trend_following(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("trend_following")
    weights = params["score_weights"]
    score_values = params["trend_score_values"]
    close = _history(prices, date_idx)
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
    momentum = _pct_return_frame(close, int(params["momentum_window"]))
    momentum_rank = pd.Series(_rank(momentum.dropna().to_dict()))
    scores = (
        trend * float(weights["trend"])
        + above_long * float(weights["above_long_ma"])
        + momentum_rank.reindex(close.columns).fillna(0.0) * float(weights["momentum"])
    )
    return _score_rows(scores, {"trend": trend, "momentum_rank": momentum_rank})


def _donchian_breakout(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("donchian_breakout")
    weights = params["score_weights"]
    close = _history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    high = _panel_history(prices, "high", date_idx)
    volume = _panel_history(prices, "volume", date_idx)
    high_window = high.tail(int(params["breakout_window"])).max().replace(0, pd.NA)
    proximity = (close.iloc[-1] / high_window * 100.0).clip(0.0, 100.0)
    volume_ratio = _volume_ratio_frame(volume, int(params["volume_window"]))
    volatility = _annualized_volatility_frame(close, int(params["volatility_window"]))
    volume_rank = pd.Series(_rank(volume_ratio.dropna().to_dict()))
    inverse_vol_rank = pd.Series(_rank((-volatility).dropna().to_dict()))
    scores = (
        proximity * float(weights["breakout_proximity"])
        + volume_rank.reindex(close.columns).fillna(0.0) * float(weights["volume"])
        + inverse_vol_rank.reindex(close.columns).fillna(0.0) * float(weights["inverse_volatility"])
    )
    return _score_rows(scores, {"breakout_proximity": proximity})


def _rps_relative_strength(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("rps_relative_strength")
    weights = params["score_weights"]
    close = _history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    short_rps = _pct_return_frame(close, int(params["short_return_window"]), skip_recent=int(params["skip_recent_window"]))
    long_rps = _pct_return_frame(close, int(params["long_return_window"]), skip_recent=int(params["skip_recent_window"]))
    trend_ma = close.tail(int(params["trend_ma_window"])).mean()
    trend_filter = pd.Series(0.0, index=close.columns).mask(close.iloc[-1] > trend_ma, 100.0)
    short_rank = pd.Series(_rank(short_rps.dropna().to_dict()))
    long_rank = pd.Series(_rank(long_rps.dropna().to_dict()))
    scores = (
        short_rank.reindex(close.columns).fillna(0.0) * float(weights["short_rps"])
        + long_rank.reindex(close.columns).fillna(0.0) * float(weights["long_rps"])
        + trend_filter * float(weights["trend_filter"])
    )
    return _score_rows(scores, {"short_rps_rank": short_rank, "long_rps_rank": long_rank})


def _sector_rotation(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("sector_rotation")
    weights = params["score_weights"]
    close = _history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    short_return = _pct_return_frame(close, int(params["short_return_window"]))
    long_return = _pct_return_frame(close, int(params["long_return_window"]))
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
        m["symbol"]: {
            "score": bounded_score(
                industry_short_rank.get(m["industry"], 0.0) * float(weights["industry_short"])
                + industry_long_rank.get(m["industry"], 0.0) * float(weights["industry_long"])
                + stock_rank.get(m["symbol"], 0.0) * float(weights["stock_inside_industry"])
            ),
            "detail": {"industry": m["industry"], "stock_rank": stock_rank.get(m["symbol"], 0.0)},
        }
        for m in metrics
    }


@lru_cache(maxsize=10000)
def _quality_sources(symbol: str) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    try:
        from data.fetchers.financial import read_financial_summary, read_valuation
    except Exception:
        return None, None
    return read_financial_summary(symbol), read_valuation(symbol)


@lru_cache(maxsize=200000)
def _quality_inputs(symbol: str, recent_period_count: int, as_of_date: str) -> dict[str, float]:
    try:
        from data.financials import extract_gross_margin_history, extract_roe_history
    except Exception:
        return {"roe": 0.0, "gross_margin": 0.0, "pe_ttm": 0.0, "pb": 0.0}

    def avg_recent(values: list[float]) -> float:
        recent = [safe_float(v) for v in values[-recent_period_count:] if safe_float(v) > 0]
        return sum(recent) / len(recent) if recent else 0.0

    def financial_as_of(df: pd.DataFrame | None, as_of: pd.Timestamp) -> pd.DataFrame | None:
        if df is None or df.empty or "报告期" not in df.columns:
            return df
        frame = df.copy()
        frame["报告期"] = pd.to_datetime(frame["报告期"], errors="coerce")
        return frame[frame["报告期"] <= as_of].sort_values("报告期")

    def latest_positive(df: pd.DataFrame | None, column: str) -> float:
        if df is None or df.empty or column not in df.columns:
            return 0.0
        frame = df.copy()
        if "trade_date" in frame.columns:
            frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
            frame = frame.sort_values("trade_date")
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        values = values[values > 0]
        return safe_float(values.iloc[-1]) if len(values) else 0.0

    as_of = pd.Timestamp(as_of_date)
    fin, valuation = _quality_sources(symbol)
    fin = financial_as_of(fin, as_of)
    if valuation is not None and not valuation.empty and "trade_date" in valuation.columns:
        valuation = valuation.copy()
        valuation["trade_date"] = pd.to_datetime(valuation["trade_date"], errors="coerce")
        valuation = valuation[valuation["trade_date"] <= as_of].sort_values("trade_date")

    return {
        "roe": avg_recent(extract_roe_history(fin)) if fin is not None else 0.0,
        "gross_margin": avg_recent(extract_gross_margin_history(fin)) if fin is not None else 0.0,
        "pe_ttm": latest_positive(valuation, "pe_ttm"),
        "pb": latest_positive(valuation, "pb"),
    }


def _quality_value(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("quality_value")
    weights = params["score_weights"]
    recent_period_count = int(params["recent_period_count"])
    try:
        as_of = pd.Timestamp(prices.index[date_idx])
    except Exception:
        as_of = pd.Timestamp(datetime.now().date())

    fin_inputs = _quality_financial_inputs(as_of.year, universe)
    valuation = _valuation_panels(universe)
    pe_ttm = _asof_row(valuation.get("pe_ttm", pd.DataFrame()), as_of).reindex(universe)
    pb = _asof_row(valuation.get("pb", pd.DataFrame()), as_of).reindex(universe)

    metrics = []
    for symbol in universe:
        inputs = fin_inputs.get(symbol, {})
        metrics.append({
            "symbol": symbol,
            "roe": _avg_recent_positive(inputs.get("roe_history", []), recent_period_count),
            "gross_margin": _avg_recent_positive(inputs.get("gross_margin_history", []), recent_period_count),
            "pe_ttm": safe_float(pe_ttm.get(symbol, 0.0)),
            "pb": safe_float(pb.get(symbol, 0.0)),
        })
    roe_rank = _rank({m["symbol"]: m["roe"] for m in metrics})
    gm_rank = _rank({m["symbol"]: m["gross_margin"] for m in metrics})
    pe_rank = _rank({m["symbol"]: -m["pe_ttm"] for m in metrics if m["pe_ttm"] > 0})
    pb_rank = _rank({m["symbol"]: -m["pb"] for m in metrics if m["pb"] > 0})
    return {
        m["symbol"]: {
            "score": bounded_score(
                roe_rank.get(m["symbol"], 0.0) * float(weights["roe"])
                + gm_rank.get(m["symbol"], 0.0) * float(weights["gross_margin"])
                + pe_rank.get(m["symbol"], 0.0) * float(weights["inverse_pe"])
                + pb_rank.get(m["symbol"], 0.0) * float(weights["inverse_pb"])
            ),
            "detail": {"roe_rank": roe_rank.get(m["symbol"], 0.0), "gross_margin_rank": gm_rank.get(m["symbol"], 0.0)},
        }
        for m in metrics
    }


def _low_vol_defensive(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("low_vol_defensive")
    weights = params["score_weights"]
    close = _history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    amount = _panel_history(prices, "amount", date_idx)
    volatility = _annualized_volatility_frame(close, int(params["volatility_window"]))
    drawdown = _drawdown_control_frame(close, int(params["drawdown_window"]))
    trend = (
        float(params["trend_score_base"])
        + _pct_return_frame(close, int(params["trend_window"])) * float(params["trend_score_scale"])
    ).clip(0.0, 100.0)
    liquidity = amount.tail(int(params["liquidity_window"])).mean()
    inverse_vol_rank = pd.Series(_rank((-volatility).dropna().to_dict()))
    liquidity_rank = pd.Series(_rank(liquidity.dropna().to_dict()))
    scores = (
        inverse_vol_rank.reindex(close.columns).fillna(0.0) * float(weights["inverse_volatility"])
        + drawdown * float(weights["drawdown_control"])
        + trend * float(weights["trend"])
        + liquidity_rank.reindex(close.columns).fillna(0.0) * float(weights["liquidity"])
    )
    return _score_rows(scores, {"inverse_vol_rank": inverse_vol_rank, "drawdown_control": drawdown})


def _volume_confirmation(universe: list[str], prices: pd.DataFrame, date_idx: int) -> dict[str, dict]:
    params = candidate_strategy_params("volume_confirmation")
    weights = params["score_weights"]
    close = _history(prices, date_idx)
    if len(close) < int(params["min_history_days"]):
        return {}
    volume = _panel_history(prices, "volume", date_idx)
    turnover = _panel_history(prices, "turnover", date_idx)
    amount = _panel_history(prices, "amount", date_idx)
    volume_ratio = _volume_ratio_frame(volume, int(params["volume_window"]))
    momentum = _pct_return_frame(close, int(params["momentum_window"]))
    flow_window = int(params["flow_window"])
    flow_proxy = turnover.tail(flow_window).mean()
    flow_proxy = flow_proxy.where(flow_proxy > 0, amount.tail(flow_window).mean())
    volume_rank = pd.Series(_rank(volume_ratio.dropna().to_dict()))
    momentum_rank = pd.Series(_rank(momentum.dropna().to_dict()))
    flow_rank = pd.Series(_rank(flow_proxy.dropna().to_dict()))
    scores = (
        volume_rank.reindex(close.columns).fillna(0.0) * float(weights["volume"])
        + momentum_rank.reindex(close.columns).fillna(0.0) * float(weights["momentum"])
        + flow_rank.reindex(close.columns).fillna(0.0) * float(weights["flow"])
    )
    return _score_rows(scores, {"volume_rank": volume_rank, "momentum_rank": momentum_rank})


_SCORERS = {
    "trend_following": _trend_following,
    "donchian_breakout": _donchian_breakout,
    "rps_relative_strength": _rps_relative_strength,
    "sector_rotation": _sector_rotation,
    "quality_value": _quality_value,
    "low_vol_defensive": _low_vol_defensive,
    "volume_confirmation": _volume_confirmation,
}


def score_candidate_strategy(name: str, universe: list[str], prices: pd.DataFrame, date_idx: int, regime: str) -> dict[str, dict]:
    if name == "regime_gated":
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

    scorer = _SCORERS.get(name)
    if scorer is None:
        return {}
    return scorer(universe, prices, date_idx)


class CandidateStrategyAlphaModel(AlphaModel):
    """Generate candidate strategy alpha from point-in-time backtest history."""

    def __init__(self, name: str, label: str, min_score: float | None = None):
        self.name = name
        self.label = label
        self.min_score = candidate_min_score(name) if min_score is None else float(min_score)

    def generate_alpha(self, universe: list[str], prices: pd.DataFrame, date_idx: int, regime: str) -> list[AlphaSignal]:
        rows = score_candidate_strategy(self.name, universe, prices, date_idx, regime)
        timestamp = datetime.now().isoformat()
        signals: list[AlphaSignal] = []
        for symbol, row in rows.items():
            score = float(row.get("score", 0.0) or 0.0)
            if score < self.min_score:
                continue
            signals.append(AlphaSignal(
                symbol=symbol,
                strategy=self.name,
                direction="buy" if score >= 50 else "hold",
                confidence=min(1.0, max(0.0, score / 100.0)),
                score=round(score, 1),
                horizon_days=20,
                reason=f"{self.label} score={score:.1f} regime={regime}",
                timestamp=timestamp,
            ))
        signals.sort(key=lambda item: item.score, reverse=True)
        return signals
