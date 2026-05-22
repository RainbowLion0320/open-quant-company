"""
MarketDataView — 强制 as-of 数据视图，消除前视偏差。

回测、训练、因子检验必须通过此视图读取历史数据，禁止直接访问完整历史。
"""

from __future__ import annotations

import pandas as pd
from datetime import datetime
from typing import Optional, Union


class MarketDataView:
    """Wraps a DataFrame with an as-of constraint — rows with date > as_of are invisible."""

    def __init__(self, df: pd.DataFrame, as_of: Union[str, datetime, pd.Timestamp], date_col: str = "date"):
        if df is None or df.empty:
            self._df = pd.DataFrame()
        else:
            df = df.copy()
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col])
                cutoff = pd.Timestamp(as_of)
                df = df[df[date_col] <= cutoff]
            self._df = df
        self.as_of = pd.Timestamp(as_of)
        self.date_col = date_col

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    @property
    def empty(self) -> bool:
        return self._df.empty

    def latest(self) -> Optional[pd.Series]:
        """Return the most recent row (closest to as_of)."""
        if self._df.empty:
            return None
        return self._df.sort_values(self.date_col).iloc[-1]

    def close(self) -> pd.Series:
        """Return close prices as a time-indexed Series."""
        if self._df.empty or "close" not in self._df.columns:
            return pd.Series(dtype=float)
        return self._df.set_index(self.date_col)["close"].sort_index()

    def ohlcv(self) -> pd.DataFrame:
        """Return OHLCV data with date index."""
        if self._df.empty:
            return pd.DataFrame()
        return self._df.set_index(self.date_col).sort_index()

    def __len__(self) -> int:
        return len(self._df)

    def __repr__(self) -> str:
        return f"MarketDataView(as_of={self.as_of.date()}, rows={len(self._df)})"


def as_of_reader(fetch_fn, as_of: Union[str, datetime, pd.Timestamp]):
    """
    Decorator/helper: given a fetch function (e.g. get_stock_daily),
    return a MarketDataView filtered to as_of.

    Usage:
        view = as_of_reader(lambda: get_stock_daily("000001"), as_of="2024-06-15")
        close_prices = view.close()
    """
    df = fetch_fn()
    return MarketDataView(df, as_of)
