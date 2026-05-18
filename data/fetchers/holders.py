"""
股东户数 + 增减持 数据获取器 — Tushare (免费, 2000分门槛)

Tushare stk_holdernumber: 全历史股东户数
Tushare stk_holdertrade: 股东增减持明细

缓存:
  data/store/stock/holders/{symbol}.parquet    — 股东户数
  data/store/stock/holdertrade/{symbol}.parquet — 增减持
"""
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

from data.datahub import get_datahub
from data.assets.stock import _to_ts_code

HUB = get_datahub()


def get_token() -> str:
    from data.tushare_utils import get_tushare_token
    return get_tushare_token()


class HolderFetcher:
    """股东户数获取器 (Tushare, 免费)"""

    def __init__(self):
        self.store_dir = HUB.store_dir("stock") / "holders"
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def fetch_symbol(self, symbol: str, force: bool = False) -> Optional[pd.DataFrame]:
        """Fetch full holder count history for one symbol via Tushare."""
        cache_path = self.store_dir / f"{symbol}.parquet"
        if cache_path.exists() and not force:
            try:
                df = HUB.read_parquet(cache_path)
                if len(df) > 0:
                    return df
            except Exception:
                pass

        import tushare as ts
        api = ts.pro_api(get_token())
        ts_code = _to_ts_code(symbol)
        if not ts_code:
            return None

        try:
            time.sleep(0.3)
            df = api.stk_holdernumber(ts_code=ts_code)
            if df is None or len(df) == 0:
                return None
            df["ann_date"] = pd.to_datetime(df["ann_date"], errors="coerce")
            df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
            df = df.sort_values("end_date")
            HUB.write_parquet(df, cache_path)
            return df
        except Exception as e:
            print(f"  [holders] {symbol}: {type(e).__name__}: {str(e)[:60]}")
            return None

    def batch_fetch(self, symbols: List[str], force: bool = False) -> Dict[str, pd.DataFrame]:
        results = {}
        for i, sym in enumerate(symbols):
            df = self.fetch_symbol(sym, force=force)
            if df is not None and len(df) > 0:
                results[sym] = df
            if (i + 1) % 100 == 0:
                print(f"  [holders] {i+1}/{len(symbols)} — {len(results)} with data")
        return results

    def get_latest(self, symbol: str) -> Optional[Dict]:
        df = self.fetch_symbol(symbol)
        if df is None or len(df) == 0:
            return None
        row = df.iloc[-1]
        return {
            "ann_date": str(row.get("ann_date", "")),
            "end_date": str(row.get("end_date", "")),
            "holder_num": int(row.get("holder_num", 0) or 0),
        }


class HolderTradeFetcher:
    """股东增减持获取器 (Tushare, 免费)"""

    def __init__(self):
        self.store_dir = HUB.store_dir("stock") / "holdertrade"
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def fetch_symbol(self, symbol: str, force: bool = False) -> Optional[pd.DataFrame]:
        """Fetch holder trade history for one symbol."""
        cache_path = self.store_dir / f"{symbol}.parquet"
        if cache_path.exists() and not force:
            try:
                df = HUB.read_parquet(cache_path)
                if len(df) > 0:
                    return df
            except Exception:
                pass

        import tushare as ts
        api = ts.pro_api(get_token())
        ts_code = _to_ts_code(symbol)
        if not ts_code:
            return None

        try:
            time.sleep(0.3)
            df = api.stk_holdertrade(ts_code=ts_code)
            if df is None or len(df) == 0:
                return None
            df["ann_date"] = pd.to_datetime(df["ann_date"], errors="coerce")
            df = df.sort_values("ann_date")
            HUB.write_parquet(df, cache_path)
            return df
        except Exception as e:
            # Some stocks may have no trade records — not an error
            return None

    def batch_fetch(self, symbols: List[str], force: bool = False) -> Dict[str, pd.DataFrame]:
        results = {}
        for i, sym in enumerate(symbols):
            df = self.fetch_symbol(sym, force=force)
            if df is not None and len(df) > 0:
                results[sym] = df
            if (i + 1) % 100 == 0:
                print(f"  [holdertrade] {i+1}/{len(symbols)} — {len(results)} with data")
        return results


def derive_holder_factors(current: Optional[int], previous: Optional[int]) -> Dict:
    """Derive concentration factors from holder count."""
    if not current or not previous or previous <= 0:
        return {}
    change_pct = (current - previous) / previous
    return {
        "holder_change_pct": round(change_pct, 6),
        "holder_concentration": round(1e8 / max(current, 1), 6),
    }
