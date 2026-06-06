"""Feature and PIT data helpers for candidate alpha backtests."""

from __future__ import annotations

import hashlib
import pickle
from functools import lru_cache

import pandas as pd

from data.storage.datahub import get_datahub
from signals.candidates.common import bounded_score, percentile_score, safe_float

_PRICE_PANELS: dict[int, dict[str, pd.DataFrame]] = {}
_VALUATION_PANELS: dict[tuple[str, ...], dict[str, pd.DataFrame]] = {}
_QUALITY_FINANCIAL_CACHE: dict[tuple[int, tuple[str, ...]], dict[str, dict]] = {}


def register_price_panels(prices: pd.DataFrame, panels: dict[str, pd.DataFrame]) -> None:
    _PRICE_PANELS[id(prices)] = panels


def transfer_price_panels(source: pd.DataFrame, target: pd.DataFrame) -> None:
    panels = _PRICE_PANELS.get(id(source))
    if panels is not None:
        _PRICE_PANELS[id(target)] = panels


def history(prices: pd.DataFrame, date_idx: int) -> pd.DataFrame:
    frame = prices.iloc[: date_idx + 1]
    frame.attrs = {}
    return frame


def panel_history(prices: pd.DataFrame, key: str, date_idx: int) -> pd.DataFrame:
    panels = _PRICE_PANELS.get(id(prices), {})
    panel = panels.get(key) if isinstance(panels, dict) else None
    if isinstance(panel, pd.DataFrame) and not panel.empty:
        frame = panel.iloc[: date_idx + 1]
        frame.attrs = {}
        return frame
    return history(prices, date_idx)


def rank_values(values: dict[str, float]) -> dict[str, float]:
    return percentile_score(pd.Series(values)) if values else {}


def pct_return_frame(close: pd.DataFrame, window: int, *, skip_recent: int = 0) -> pd.Series:
    if len(close) < window + skip_recent + 1:
        return pd.Series(dtype="float64")
    end_idx = -1 - skip_recent if skip_recent else -1
    start_idx = end_idx - window
    base = pd.to_numeric(close.iloc[start_idx], errors="coerce")
    latest = pd.to_numeric(close.iloc[end_idx], errors="coerce")
    return latest / base.replace(0, pd.NA) - 1.0


def annualized_volatility_frame(close: pd.DataFrame, window: int, default: float = 0.30) -> pd.Series:
    if len(close) < window + 1:
        return pd.Series(default, index=close.columns, dtype="float64")
    returns = close.pct_change().tail(window)
    return returns.std().fillna(default) * (252 ** 0.5)


def volume_ratio_frame(volume: pd.DataFrame, window: int) -> pd.Series:
    if len(volume) < window + 1:
        return pd.Series(1.0, index=volume.columns, dtype="float64")
    base = volume.iloc[-window - 1 : -1].mean().replace(0, pd.NA)
    return (volume.iloc[-1] / base).fillna(1.0)


def drawdown_control_frame(close: pd.DataFrame, window: int) -> pd.Series:
    if len(close) < 2:
        return pd.Series(0.0, index=close.columns, dtype="float64")
    recent = close.tail(window)
    drawdown = (recent / recent.cummax() - 1.0).min()
    return (100.0 + drawdown.fillna(0.0) * 250.0).clip(0.0, 100.0)


def score_rows(scores: pd.Series, detail: dict[str, pd.Series] | None = None) -> dict[str, dict]:
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


def avg_recent_positive(values: list[float], period_count: int) -> float:
    recent = [safe_float(value) for value in values[-period_count:] if safe_float(value) > 0]
    return sum(recent) / len(recent) if recent else 0.0


def asof_row(frame: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="float64")
    idx = frame.index.searchsorted(as_of, side="right") - 1
    if idx < 0:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame.iloc[idx], errors="coerce")


def quality_financial_inputs(year: int, universe: list[str]) -> dict[str, dict]:
    key = (int(year), tuple(universe))
    if key not in _QUALITY_FINANCIAL_CACHE:
        from backtest.buffett_real_scorer import build_pit_financial_inputs

        _QUALITY_FINANCIAL_CACHE[key] = build_pit_financial_inputs(
            year,
            universe,
            log_label="质量价值",
        )
    return _QUALITY_FINANCIAL_CACHE[key]


def valuation_panels(universe: list[str]) -> dict[str, pd.DataFrame]:
    symbols = tuple(universe)
    if symbols in _VALUATION_PANELS:
        return _VALUATION_PANELS[symbols]

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
    cache_dir = hub.cache_root / "backtest"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"backtest_valuation_matrix_{cache_key}.pkl"
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


@lru_cache(maxsize=10000)
def quality_sources(symbol: str) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    try:
        from data.ingestion.fetchers.financial import read_financial_summary, read_valuation
    except Exception:
        return None, None
    return read_financial_summary(symbol), read_valuation(symbol)


@lru_cache(maxsize=200000)
def quality_inputs(symbol: str, recent_period_count: int, as_of_date: str) -> dict[str, float]:
    try:
        from data.market.financials import extract_gross_margin_history, extract_roe_history
    except Exception:
        return {"roe": 0.0, "gross_margin": 0.0, "pe_ttm": 0.0, "pb": 0.0}

    def avg_recent(values: list[float]) -> float:
        recent = [safe_float(value) for value in values[-recent_period_count:] if safe_float(value) > 0]
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
    fin, valuation = quality_sources(symbol)
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
