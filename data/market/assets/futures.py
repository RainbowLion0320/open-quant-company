"""
Futures Asset Adapter — 多资产第四实现

数据源:
  - AKShare futures_main_sina (主力连续合约, 日频)
  - 覆盖: 股指(IF/IC/IH), 国债(T/TF/TS), 商品(RB/AU/CU/SC)

因子:
  - 基差: 现货-期货价差
  - 期限结构: 近月-远月
  - 持仓量变化
  - 波动率
"""
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import time
from pathlib import Path

from data.market.assets.base import AssetAdapter
from data.storage.datahub import get_datahub

HUB = get_datahub()


# ── Futures universe: main contracts ──
FUTURES_UNIVERSE = [
    # 股指期货
    "IF",   # 沪深300股指
    "IC",   # 中证500股指
    "IH",   # 上证50股指
    "IM",   # 中证1000股指
    # 国债期货
    "T",    # 10年期国债
    "TF",   # 5年期国债
    "TS",   # 2年期国债
    # 商品
    "RB",   # 螺纹钢
    "AU",   # 黄金
    "CU",   # 铜
    "SC",   # 原油
]

FUTURES_NAMES = {
    "IF": "沪深300股指", "IC": "中证500股指",
    "IH": "上证50股指", "IM": "中证1000股指",
    "T": "10年国债期货", "TF": "5年国债期货", "TS": "2年国债期货",
    "RB": "螺纹钢", "AU": "黄金期货", "CU": "铜", "SC": "原油",
}

FUTURES_CATEGORY = {
    "IF": "equity_index", "IC": "equity_index", "IH": "equity_index", "IM": "equity_index",
    "T": "bond", "TF": "bond", "TS": "bond",
    "RB": "commodity", "AU": "commodity", "CU": "commodity", "SC": "commodity",
}


class FuturesAsset(AssetAdapter):
    """Futures asset adapter: main continuous contracts."""

    asset_type: str = "futures"
    label: str = "期货"
    description: str = "股指/国债/商品主力连续合约"
    DATA_SOURCE: str = "real"
    DATA_SOURCE_DETAIL: str = "AKShare futures_main_sina (主力连续合约, 日频)"
    TRADING_CALENDAR: str = "CFFEX/SHFE/DCE"
    ROLLOVER_RULE: str = "continuous_main"
    TRADABLE: bool = False  # data available but not yet integrated with broker/exchange
    RESEARCH_READY: bool = True
    # Contract multipliers for margin and PnL calculation
    CONTRACT_MULTIPLIER: float = 1.0  # per-symbol; use get_metadata() for specific
    _MULTIPLIERS: dict = {
        "IF": 300, "IC": 200, "IH": 300, "IM": 200,  # equity index
        "T": 10000, "TF": 10000, "TS": 20000,         # government bond
        "RB": 10, "AU": 1000, "CU": 5, "SC": 1000,    # commodity
    }

    def __init__(self, store_root: Path | str | None = None):
        super().__init__(store_root)
        self._universe = list(FUTURES_UNIVERSE)

    def get_data_source(self, symbol: str = "") -> dict:
        """Override: per-symbol contract multiplier."""
        base = super().get_data_source(symbol)
        m = self._MULTIPLIERS.get(symbol)
        if m:
            base["multiplier"] = m
            base["detail"] = f"{base['detail']} (乘数={m})"
        return base

    def fetch_daily(
        self, symbol: str, start_date: str = "20180101", end_date: str = "",
    ) -> Optional[pd.DataFrame]:
        """Fetch daily OHLCV via AKShare futures_main_sina."""
        cache_path = self.cache_path(symbol)
        if cache_path.exists():
            try:
                return HUB.read_parquet(cache_path)
            except Exception:
                pass

        try:
            import akshare as ak
            import os as _os
            for k in list(_os.environ.keys()):
                if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
                    del _os.environ[k]
            _os.environ.setdefault('no_proxy', '*')
            time.sleep(1.0)

            # Note: some symbols need '0' suffix (e.g., 'IF0'), some don't
            sym_key = f"{symbol}0"
            try:
                df = ak.futures_main_sina(symbol=sym_key)
            except Exception:
                df = ak.futures_main_sina(symbol=symbol)

            if df is None or len(df) == 0:
                return None

            # Normalize columns
            col_map = {
                "日期": "date", "开盘价": "open", "最高价": "high",
                "最低价": "low", "收盘价": "close", "成交量": "volume",
                "持仓量": "open_interest",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            df = df.sort_index()

            # Keep only OHLCV + OI
            keep = [c for c in ["open", "high", "low", "close", "volume", "open_interest"] if c in df.columns]
            df = df[keep]
            HUB.write_parquet(df, cache_path, index=True)
            return df
        except Exception as e:
            print(f"  [Futures] {symbol}: {type(e).__name__}: {str(e)[:60]}")
            return None

    def fetch_fundamentals(self, symbol: str) -> Dict:
        """Futures fundamentals: open interest, volume, basis (approximated)."""
        df = self.fetch_daily(symbol)
        if df is None or len(df) < 5:
            return {}
        latest = df.iloc[-1]
        return {
            "close": float(latest.get("close", 0)),
            "volume": float(latest.get("volume", 0)),
            "open_interest": float(latest.get("open_interest", 0)),
        }

    def get_universe(self) -> List[str]:
        return self._universe

    def get_metadata(self, symbol: str) -> Dict:
        name = FUTURES_NAMES.get(symbol, symbol)
        category = FUTURES_CATEGORY.get(symbol, "commodity")
        return {
            "name": name, "industry": category,
            "sector": category, "asset_type": "futures",
        }

    def __repr__(self) -> str:
        return f"<FuturesAsset: {len(self._universe)} contracts>"
