"""
资金流向数据获取器 — AKShare (免费, 同花顺数据源)

AKShare stock_individual_fund_flow: 近100交易日个股资金流向
缓存: var/store/stock/moneyflow/{symbol}.parquet

列:
  日期, 收盘价, 涨跌幅,
  主力净流入-净额, 主力净流入-净占比,
  超大单净流入-净额, 超大单净流入-净占比,
  大单净流入-净额, 大单净流入-净占比,
  中单净流入-净额, 中单净流入-净占比,
  小单净流入-净额, 小单净流入-净占比
"""
import time
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

from data.storage.datahub import get_datahub

HUB = get_datahub()


class MoneyflowFetcher:
    """个股资金流向获取器 (AKShare, 免费无限)"""

    def __init__(self):
        self.store_dir = HUB.store_dir("stock") / "moneyflow"
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def fetch_symbol(self, symbol: str, force: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetch moneyflow history for one symbol.
        Caches to Parquet. Returns up to ~120 trading days.
        """
        cache_path = self.store_dir / f"{symbol}.parquet"
        if cache_path.exists() and not force:
            try:
                df = HUB.read_parquet(cache_path)
                # If cache is fresh (within 1 day), reuse
                if len(df) > 0:
                    last_date = pd.to_datetime(df["日期"].iloc[-1])
                    if (pd.Timestamp.now() - last_date).days <= 1:
                        return df
            except Exception:
                pass

        import akshare as ak
        market = "sz" if symbol.startswith(("0", "3")) else "sh"

        try:
            time.sleep(0.5)  # Respect rate limits
            df = ak.stock_individual_fund_flow(stock=symbol, market=market)
            if df is None or len(df) == 0:
                return None

            # Normalize columns
            df["日期"] = pd.to_datetime(df["日期"])
            df = df.sort_values("日期")
            HUB.write_parquet(df, cache_path)
            return df
        except Exception as e:
            print(f"  [moneyflow] {symbol}: {type(e).__name__}: {str(e)[:80]}")
            return None

    def batch_fetch(self, symbols: List[str], force: bool = False) -> Dict[str, pd.DataFrame]:
        """Batch fetch moneyflow for multiple symbols."""
        results = {}
        for i, sym in enumerate(symbols):
            df = self.fetch_symbol(sym, force=force)
            if df is not None and len(df) > 0:
                results[sym] = df
            if (i + 1) % 20 == 0:
                print(f"  [moneyflow] progress: {i+1}/{len(symbols)}")
        return results

    def get_latest(self, symbol: str) -> Dict:
        """Get latest moneyflow data for a symbol."""
        df = self.fetch_symbol(symbol)
        if df is None or len(df) == 0:
            return {}

        row = df.iloc[-1]
        return {
            "date": str(row.get("日期", "")),
            "close": float(row.get("收盘价", 0) or 0),
            "pct_chg": float(row.get("涨跌幅", 0) or 0),
            "main_net": float(row.get("主力净流入-净额", 0) or 0),
            "main_net_pct": float(row.get("主力净流入-净占比", 0) or 0),
            "super_lg_net": float(row.get("超大单净流入-净额", 0) or 0),
            "super_lg_pct": float(row.get("超大单净流入-净占比", 0) or 0),
            "lg_net": float(row.get("大单净流入-净额", 0) or 0),
            "lg_net_pct": float(row.get("大单净流入-净占比", 0) or 0),
            "md_net": float(row.get("中单净流入-净额", 0) or 0),
            "md_net_pct": float(row.get("中单净流入-净占比", 0) or 0),
            "sm_net": float(row.get("小单净流入-净额", 0) or 0),
            "sm_net_pct": float(row.get("小单净流入-净占比", 0) or 0),
        }


def derive_moneyflow_factors(mf: Dict) -> Dict:
    """
    Derive alpha factors from moneyflow data.

    Key insight: 主力净流入持续为正 = 机构建仓信号
    小单净流入持续为正 = 散户接盘信号

    Returns factor_name → value dict.
    """
    if not mf:
        return {}

    # Main force net flow ratio (already in % form from AKShare)
    main_pct = mf.get("main_net_pct", 0)

    # Super-large + large combined = institutional
    inst_net = (mf.get("super_lg_net", 0) + mf.get("lg_net", 0))

    # Retail = small + medium
    retail_net = (mf.get("sm_net", 0) + mf.get("md_net", 0))

    # Smart money ratio: institutional / total absolute flow
    total_abs = abs(inst_net) + abs(retail_net) + 1  # avoid div0
    smart_ratio = inst_net / total_abs

    return {
        "mf_main_net_pct": round(main_pct, 4),
        "mf_inst_net": round(inst_net / 1e8, 4),      # 亿元
        "mf_retail_net": round(retail_net / 1e8, 4),  # 亿元
        "mf_smart_ratio": round(smart_ratio, 4),
    }
