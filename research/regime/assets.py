"""Tradable asset panel builders for profit-oriented regime research."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from research.regime.features import normalize_ohlcv

def build_tradable_asset_panel(
    equity_df: pd.DataFrame,
    defensive_df: pd.DataFrame | None = None,
    *,
    start: str | None = None,
    end: str | None = None,
    equity_source: str = "equity",
    defensive_source: str | None = None,
) -> pd.DataFrame:
    """Build a local tradable asset panel for profit-oriented regime research."""
    equity = normalize_ohlcv(equity_df)
    if start:
        equity = equity[equity.index >= pd.Timestamp(start)]
    if end and end != "auto":
        equity = equity[equity.index <= pd.Timestamp(end)]
    if equity.empty:
        panel = pd.DataFrame(columns=["equity_close", "equity_return", "cash_return", "defensive_return"])
        panel.attrs["asset_sources"] = {"equity": equity_source, "defensive": "cash_fallback", "cash": "zero_cash"}
        panel.attrs["notes"] = ["insufficient_data: equity proxy unavailable", "defensive_unavailable"]
        return panel

    panel = pd.DataFrame(index=equity.index)
    panel["equity_close"] = equity["close"].astype(float)
    panel["equity_return"] = panel["equity_close"].pct_change().fillna(0.0)
    panel["cash_return"] = 0.0
    notes: list[str] = []

    if defensive_df is not None and not defensive_df.empty:
        defensive = normalize_ohlcv(defensive_df)
        defensive_return = defensive["close"].astype(float).pct_change().reindex(panel.index).ffill().fillna(0.0)
        panel["defensive_return"] = defensive_return
        defensive_name = defensive_source or "defensive_proxy"
    else:
        panel["defensive_return"] = panel["cash_return"]
        defensive_name = "cash_fallback"
        notes.append("defensive_unavailable")

    panel = panel.replace([np.inf, -np.inf], np.nan).dropna(subset=["equity_close"])
    panel.attrs["asset_sources"] = {"equity": equity_source, "defensive": defensive_name, "cash": "zero_cash"}
    panel.attrs["notes"] = notes
    return panel[["equity_close", "equity_return", "cash_return", "defensive_return"]]


def _read_local_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def load_local_equity_ohlcv(symbol: str = "sh000001", *, data_root: str | Path = ".") -> tuple[pd.DataFrame, str, list[str]]:
    """Load a broad equity proxy from local cache/parquet without network fetches."""
    notes: list[str] = []
    if symbol.startswith(("sh", "sz")):
        try:
            from data.fetcher import _read_cache

            cached = _read_cache(f"index_daily_{symbol}_default", max_age_hours=0)
            if cached is not None and len(cached) > 0:
                return cached, f"local_cache:{symbol}", notes
        except Exception as exc:
            notes.append(f"index_cache_unavailable:{type(exc).__name__}")

    root = Path(data_root)
    fallbacks = [
        (root / "data/store/fund/daily/510300.SH.parquet", "fund_daily:510300.SH"),
        (root / "data/store/fund/daily/510500.SH.parquet", "fund_daily:510500.SH"),
        (root / "data/store/fund/daily/510050.SH.parquet", "fund_daily:510050.SH"),
    ]
    for path, source in fallbacks:
        frame = _read_local_parquet(path)
        if not frame.empty:
            notes.append(f"equity_symbol_{symbol}_not_found_used_{source}")
            return frame, source, notes
    notes.append(f"equity_proxy_unavailable:{symbol}")
    return pd.DataFrame(), "", notes


def _load_treasury_defensive_proxy(*, data_root: str | Path = ".") -> tuple[pd.DataFrame, str, list[str]]:
    path = Path(data_root) / "data/store/bond/treasury_yields.parquet"
    frame = _read_local_parquet(path)
    if frame.empty or "中国国债收益率10年" not in frame.columns:
        return pd.DataFrame(), "", ["bond_proxy_unavailable"]
    data = frame.copy()
    if "date" in data.columns:
        dates = pd.to_datetime(data["date"], errors="coerce")
    elif "日期" in data.columns:
        dates = pd.to_datetime(data["日期"], errors="coerce")
    else:
        dates = pd.to_datetime(data.index, errors="coerce")
    yld = pd.to_numeric(data["中国国债收益率10年"], errors="coerce")
    proxy = pd.DataFrame({"date": pd.Series(dates).to_numpy(), "yield": pd.Series(yld).to_numpy()}).dropna().sort_values("date")
    if proxy.empty:
        return pd.DataFrame(), "", ["bond_proxy_unavailable"]
    rate = proxy["yield"] / 100.0
    duration = 7.0
    daily_return = (rate.shift(1).fillna(rate) / 252.0) - duration * rate.diff().fillna(0.0)
    daily_return = daily_return.clip(-0.03, 0.03).fillna(0.0)
    close = (1.0 + daily_return).cumprod() * 100.0
    return pd.DataFrame({"date": proxy["date"], "close": close}), "cn_10y_treasury_proxy", []


def load_tradable_asset_panel(
    start: str | None = None,
    end: str | None = "auto",
    *,
    symbol: str = "sh000001",
    data_root: str | Path = ".",
) -> pd.DataFrame:
    """Load the best local tradable panel available; never fetches network data."""
    equity_df, equity_source, equity_notes = load_local_equity_ohlcv(symbol, data_root=data_root)
    defensive_df, defensive_source, defensive_notes = _load_treasury_defensive_proxy(data_root=data_root)
    panel = build_tradable_asset_panel(
        equity_df,
        defensive_df if not defensive_df.empty else None,
        start=start,
        end=end,
        equity_source=equity_source or symbol,
        defensive_source=defensive_source or None,
    )
    panel.attrs["notes"] = list(panel.attrs.get("notes", [])) + equity_notes + defensive_notes
    return panel
