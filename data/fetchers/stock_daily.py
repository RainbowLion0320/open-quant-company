"""
stock_daily.py — OHLCV 日线数据拉取 + 本地 parquet 存储

职责:
  fetch_all(pool_symbols) — cron 调用，批量拉取全池日线
  fetch_one(symbol)       — 单只拉取/刷新
  read_one(symbol)        — 纯读本地 parquet (消费者唯一入口)

消费者永远调用 read_one()，不接触 API。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Sequence

import pandas as pd

from data.datahub import get_datahub
from data.fetchers.base import throttle
from data.symbol_utils import normalize_symbol, to_sina_symbol

HUB = get_datahub()


def _to_sina(symbol: str) -> str:
    """'600519' → 'sh600519'"""
    return to_sina_symbol(symbol)


def _to_plain(symbol: str) -> str:
    return normalize_symbol(symbol)


def fetch_one(
    symbol: str,
    source: str = "sina",
    adjust: str = "qfq",
    force: bool = False,
) -> Optional[pd.DataFrame]:
    """
    从 AKShare 拉取单只股票全量日线，写入 store/stock/daily/{symbol}.parquet

    返回 DataFrame 或 None。
    """
    symbol = normalize_symbol(symbol)
    path = HUB.stock_daily_path(symbol)

    # 如果文件已存在且不强制，增量更新
    if path.exists() and not force:
        old = HUB.read_parquet(path)
        if old is not None and len(old) > 0 and "date" in old.columns:
            last_date = old["date"].iloc[-1]
            if isinstance(last_date, str):
                last_date = pd.to_datetime(last_date)
            if last_date >= pd.to_datetime(date.today() - timedelta(days=1)):
                # 数据已经是最新的
                return old

    import akshare as ak

    throttle()
    try:
        if source == "sina":
            df = ak.stock_zh_a_daily(symbol=_to_sina(symbol), adjust=adjust)
            df = df.rename(columns={
                "date": "date", "open": "open", "close": "close",
                "high": "high", "low": "low", "volume": "volume",
                "amount": "amount", "outstanding_share": "outstanding_share",
                "turnover": "turnover",
            })
        elif source == "tx":
            df = ak.stock_zh_a_hist_tx(
                symbol=_to_sina(symbol),
                start_date="19900101",
                end_date=date.today().strftime("%Y%m%d"),
            )
            df = df.rename(columns={
                "date": "date", "open": "open", "close": "close",
                "high": "high", "low": "low", "amount": "volume",
            })
        else:
            df = ak.stock_zh_a_hist(symbol=_to_plain(symbol), period="daily", adjust=adjust)
            df = df.rename(columns={
                "日期": "date", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume",
                "成交额": "amount", "振幅": "amplitude",
                "涨跌幅": "pct_change", "涨跌额": "change",
                "换手率": "turnover",
            })

        # 列名标准化
        for col in ["date", "open", "close", "high", "low", "volume", "amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce") if col != "date" else pd.to_datetime(df[col], errors="coerce")

        HUB.write_parquet(df, path)
        return df
    except Exception as e:
        print(f"  [FAIL] fetch_one({symbol}) — {e}")
        return None


def read_one(symbol: str) -> Optional[pd.DataFrame]:
    """
    纯本地读取 — 消费者唯一入口。不从 API 拉。
    """
    symbol = normalize_symbol(symbol)
    return HUB.read_parquet(HUB.stock_daily_path(symbol))


def fetch_all(
    symbols: Sequence[str],
    source: str = "sina",
    adjust: str = "qfq",
) -> dict[str, Optional[pd.DataFrame]]:
    """
    批量拉取全池日线。cron 调用。
    返回 {symbol: DataFrame | None}。
    """
    results = {}
    total = len(symbols)
    for i, sym in enumerate(symbols):
        if (i + 1) % 100 == 0:
            print(f"  [{i+1}/{total}] {sym} ...")
        results[sym] = fetch_one(sym, source=source, adjust=adjust)
    return results
