"""Unified stock price access with explicit adjustment semantics."""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import Iterable

import pandas as pd

from data.storage.datahub import DataHub, get_datahub
from data.market.price_types import (
    PriceFrameMetadata,
    PriceMode,
    PriceUseCase,
    attach_price_metadata,
    mode_for_use_case,
    normalize_price_mode,
    normalize_price_use_case,
)


OHLC_COLUMNS = ("open", "high", "low", "close")
PANEL_COLUMNS = ("high", "volume", "amount", "turnover")


def price_mode_for_use_case(use_case: str | PriceUseCase) -> str:
    return mode_for_use_case(use_case).value


def _date_series(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_datetime(frame[column], errors="coerce")


def _normalize_daily_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce")
        out = out.dropna(subset=["date"]).sort_values("date")
    for column in set(OHLC_COLUMNS + PANEL_COLUMNS):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def _normalize_adj_factor(adj_factor: pd.DataFrame) -> pd.DataFrame:
    if adj_factor is None or adj_factor.empty:
        return pd.DataFrame(columns=["date", "adj_factor"])
    out = adj_factor.copy()
    date_col = "trade_date" if "trade_date" in out.columns else "date"
    if date_col not in out.columns or "adj_factor" not in out.columns:
        return pd.DataFrame(columns=["date", "adj_factor"])
    out["date"] = _date_series(out, date_col)
    out["adj_factor"] = pd.to_numeric(out["adj_factor"], errors="coerce")
    out = out.dropna(subset=["date", "adj_factor"]).sort_values("date")
    return out[["date", "adj_factor"]].drop_duplicates(subset=["date"], keep="last")


def adjust_ohlcv(raw: pd.DataFrame, adj_factor: pd.DataFrame, mode: str | PriceMode = PriceMode.QFQ) -> pd.DataFrame:
    """Adjust raw OHLCV with Tushare-style adjustment factors.

    qfq: price * factor / latest_factor
    hfq: price * factor
    raw: returned unchanged
    """
    price_mode = normalize_price_mode(mode)
    base = _normalize_daily_frame(raw)
    if price_mode == PriceMode.RAW:
        return base
    if base.empty or "date" not in base.columns:
        return base

    adj = _normalize_adj_factor(adj_factor)
    if adj.empty:
        raise ValueError("adj_factor data is required to derive adjusted prices")

    merged = base.merge(adj, on="date", how="left")
    merged["adj_factor"] = merged["adj_factor"].ffill().bfill()
    latest_factor = float(merged["adj_factor"].dropna().iloc[-1])
    ratio = merged["adj_factor"] if price_mode == PriceMode.HFQ else merged["adj_factor"] / latest_factor
    out = base.copy()
    for column in OHLC_COLUMNS:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce") * ratio.to_numpy()
    return out


def _read_adjusted_provider_frame(symbol: str, mode: PriceMode, hub: DataHub) -> pd.DataFrame:
    path = hub.stock_daily_path(symbol) if mode == PriceMode.QFQ else hub.stock_daily_hfq_path(symbol)
    df = hub.read_parquet(path, default=pd.DataFrame())
    if df is None or df.empty:
        return pd.DataFrame()
    df = _normalize_daily_frame(df)
    attach_price_metadata(
        df,
        PriceFrameMetadata(
            requested_mode=mode,
            actual_mode=mode,
            source="local_parquet",
            adjustment_source="provider_adjusted",
        ),
    )
    return df


def _read_raw_frame(symbol: str, hub: DataHub) -> pd.DataFrame:
    raw = hub.read_parquet(hub.stock_daily_raw_path(symbol), default=pd.DataFrame())
    if raw is None or raw.empty:
        return pd.DataFrame()
    raw = _normalize_daily_frame(raw)
    attach_price_metadata(
        raw,
        PriceFrameMetadata(
            requested_mode=PriceMode.RAW,
            actual_mode=PriceMode.RAW,
            source="local_parquet",
            adjustment_source="raw",
        ),
    )
    return raw


def _read_adj_factor(symbol: str, hub: DataHub) -> pd.DataFrame:
    return hub.read_parquet(hub.stock_adj_factor_path(symbol), default=pd.DataFrame())


def _slice_dates(frame: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if frame.empty or "date" not in frame.columns:
        return frame
    out = frame.copy()
    if start:
        out = out[out["date"] >= pd.Timestamp(start)]
    if end:
        out = out[out["date"] <= pd.Timestamp(end)]
    return out


def get_stock_prices(
    symbol: str,
    mode: str | PriceMode = PriceMode.QFQ,
    *,
    use_case: str | PriceUseCase | None = None,
    start: str | None = None,
    end: str | None = None,
    hub: DataHub | None = None,
    allow_adjusted_fallback: bool = True,
    strict: bool = False,
) -> pd.DataFrame:
    """Return stock OHLCV with explicit raw/qfq/hfq semantics."""
    store = hub or get_datahub()
    requested = mode_for_use_case(use_case) if use_case is not None else normalize_price_mode(mode)

    if requested == PriceMode.RAW:
        raw = _read_raw_frame(symbol, store)
        if not raw.empty:
            return _slice_dates(raw, start, end)
        if allow_adjusted_fallback:
            fallback = _read_adjusted_provider_frame(symbol, PriceMode.QFQ, store)
            if not fallback.empty:
                attach_price_metadata(
                    fallback,
                    PriceFrameMetadata(
                        requested_mode=PriceMode.RAW,
                        actual_mode=PriceMode.QFQ,
                        source="local_parquet",
                        adjustment_source="provider_adjusted",
                        fallback_reason="raw_unavailable_latest_qfq_compatible",
                    ),
                )
                return _slice_dates(fallback, start, end)
        if strict:
            raise FileNotFoundError(f"raw stock prices not found for {symbol}")
        return pd.DataFrame()

    raw = _read_raw_frame(symbol, store)
    if not raw.empty:
        try:
            adjusted = adjust_ohlcv(raw, _read_adj_factor(symbol, store), requested)
            attach_price_metadata(
                adjusted,
                PriceFrameMetadata(
                    requested_mode=requested,
                    actual_mode=requested,
                    source="derived",
                    adjustment_source="adj_factor",
                ),
            )
            return _slice_dates(adjusted, start, end)
        except Exception:
            if strict:
                raise

    provider = _read_adjusted_provider_frame(symbol, requested, store)
    if not provider.empty:
        return _slice_dates(provider, start, end)
    if strict:
        raise FileNotFoundError(f"{requested.value} stock prices not found for {symbol}")
    return pd.DataFrame()


def get_latest_price(
    symbol: str,
    *,
    mode: str | PriceMode = PriceMode.RAW,
    use_case: str | PriceUseCase | None = None,
    hub: DataHub | None = None,
) -> float:
    prices = get_stock_prices(symbol, mode=mode, use_case=use_case, hub=hub)
    if prices.empty or "close" not in prices.columns:
        return 0.0
    close = pd.to_numeric(prices.sort_values("date")["close"], errors="coerce").dropna()
    return float(close.iloc[-1]) if len(close) else 0.0


def get_stock_price_matrix(
    symbols: Iterable[str],
    *,
    mode: str | PriceMode = PriceMode.QFQ,
    use_case: str | PriceUseCase | None = None,
    start: str | None = None,
    end: str | None = None,
    min_bars: int = 200,
    hub: DataHub | None = None,
    cache_dir: str | Path | None = None,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    store = hub or get_datahub()
    requested = mode_for_use_case(use_case) if use_case is not None else normalize_price_mode(mode)
    symbol_list = list(symbols)

    latest_mtime = 0
    for symbol in symbol_list:
        for path in (
            store.stock_daily_raw_path(symbol),
            store.stock_daily_path(symbol),
            store.stock_daily_hfq_path(symbol),
            store.stock_adj_factor_path(symbol),
        ):
            if path.exists():
                latest_mtime = max(latest_mtime, path.stat().st_mtime_ns)
    cache_root = Path(cache_dir) if cache_dir else store.cache_root / "backtest"
    cache_root.mkdir(parents=True, exist_ok=True)
    symbol_digest = hashlib.md5("|".join(symbol_list).encode()).hexdigest()[:12]
    cache_key = hashlib.md5(
        f"matrix|{requested.value}|{start}|{end}|{min_bars}|{symbol_digest}|{latest_mtime}".encode()
    ).hexdigest()[:12]
    cache_path = cache_root / f"price_matrix_{requested.value}_{cache_key}.pkl"
    if cache_path.exists():
        with open(cache_path, "rb") as f:
            cached = pickle.load(f)
        return cached["prices"], cached.get("panels", {})

    close_map: dict[str, pd.Series] = {}
    panel_maps: dict[str, dict[str, pd.Series]] = {column: {} for column in PANEL_COLUMNS}
    for symbol in symbol_list:
        df = get_stock_prices(symbol, mode=requested, start=start, end=end, hub=store)
        if df.empty or len(df) < min_bars or "date" not in df.columns or "close" not in df.columns:
            continue
        indexed = df.set_index("date").sort_index()
        close_map[symbol] = pd.to_numeric(indexed["close"], errors="coerce").rename(symbol)
        for column in PANEL_COLUMNS:
            if column in indexed.columns:
                panel_maps[column][symbol] = pd.to_numeric(indexed[column], errors="coerce").rename(symbol)
            else:
                panel_maps[column][symbol] = close_map[symbol]

    if not close_map:
        return pd.DataFrame(), {}
    prices = pd.concat(close_map.values(), axis=1, keys=close_map.keys())
    panels = {
        column: pd.concat(values.values(), axis=1, keys=values.keys()).reindex(prices.index)
        for column, values in panel_maps.items()
        if values
    }
    attach_price_metadata(
        prices,
        PriceFrameMetadata(
            requested_mode=requested,
            actual_mode=requested,
            source="price_matrix",
            adjustment_source="mixed_source",
        ),
    )
    cache_root.mkdir(parents=True, exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump({"prices": prices, "panels": panels}, f)
    return prices, panels
