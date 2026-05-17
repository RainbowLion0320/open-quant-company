"""
Bond Asset Adapter — 多资产第三实现

数据源:
  - AKShare bond_zh_us_rate (国债收益率曲线, 2/5/10/30Y, 日频)
  - AKShare bond_cb_jsl (可转债行情, 实时快照)

因子:
  - 收益率水平: 10Y yield
  - 期限利差: 10Y-2Y spread
  - 收益率变化: daily yield change
  - 可转债: 转股溢价率, 纯债溢价率, 平价

Note: 国债收益率数据是价格代理——不是ETF价格，是市场利率。
债券价格 ≈ -久期 × 收益率变化。ETF proxy 在 tournament 中用收益率构造。
"""
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import time
from pathlib import Path

from data.assets.base import AssetAdapter
from data.datahub import get_datahub

HUB = get_datahub()


# ── Bond universe ──
BOND_UNIVERSE = [
    # 国债关键期限
    "CN2Y",   # 2年期国债
    "CN5Y",   # 5年期国债
    "CN10Y",  # 10年期国债 (最活跃)
    "CN30Y",  # 30年期国债
    # 可转债 (有成交量的)
    "110059", # 浦发转债
    "113044", # 大秦转债
    "110079", # 杭银转债
    "113050", # 南银转债
    "127018", # 本钢转债
]

BOND_NAMES = {
    "CN2Y": "2年期国债", "CN5Y": "5年期国债",
    "CN10Y": "10年期国债", "CN30Y": "30年期国债",
    "110059": "浦发转债", "113044": "大秦转债",
    "110079": "杭银转债", "113050": "南银转债",
    "127018": "本钢转债",
}

YIELD_COLUMNS = {
    "CN2Y": "中国国债收益率2年",
    "CN5Y": "中国国债收益率5年",
    "CN10Y": "中国国债收益率10年",
    "CN30Y": "中国国债收益率30年",
}


class BondAsset(AssetAdapter):
    """Bond asset adapter: treasury yields + convertible bonds."""

    asset_type: str = "bond"
    label: str = "债券"
    description: str = "国债收益率曲线 + 可转债"

    def __init__(self, store_root: Path | str | None = None):
        super().__init__(store_root)
        self._universe = list(BOND_UNIVERSE)
        self._yield_cache: Optional[pd.DataFrame] = None

    def _load_yields(self) -> Optional[pd.DataFrame]:
        """Load full treasury yield curve, cached."""
        if self._yield_cache is not None:
            return self._yield_cache
        cache = self.asset_dir / "treasury_yields.parquet"
        if cache.exists():
            self._yield_cache = HUB.read_parquet(cache)
            return self._yield_cache
        try:
            import akshare as ak
            import os as _os
            for k in list(_os.environ.keys()):
                if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
                    del _os.environ[k]
            _os.environ.setdefault('no_proxy', '*')
            df = ak.bond_zh_us_rate()
            df["date"] = pd.to_datetime(df["日期"])
            df = df.set_index("date").sort_index()
            HUB.write_parquet(df, cache, index=True)
            self._yield_cache = df
            return df
        except Exception as e:
            print(f"  [Bond] yield load failed: {e}")
            return None

    def fetch_daily(
        self, symbol: str, start_date: str = "20180101", end_date: str = "",
    ) -> Optional[pd.DataFrame]:
        """
        Fetch daily data for a bond symbol.
        For treasury codes (CN2Y etc.): yield → synthetic price.
        For convertible codes: real price from bond_cb_jsl.
        """
        if symbol in YIELD_COLUMNS:
            df = self._load_yields()
            if df is None:
                return None
            col = YIELD_COLUMNS[symbol]
            if col not in df.columns:
                return None
            yld = df[col].dropna() / 100.0
            # Synthetic price: base=100, return ≈ -duration × yield_change
            duration = {"CN2Y": 2.0, "CN5Y": 5.0, "CN10Y": 7.0, "CN30Y": 15.0}[symbol]
            rets = -duration * yld.diff().fillna(0)
            price = 100.0 * (1 + rets).cumprod()
            result = pd.DataFrame({"close": price, "yield": yld * 100}, index=price.index)
            return result

        # Convertible bond: use spot data (snapshot, not full history)
        try:
            import akshare as ak
            df = ak.bond_cb_jsl(cookie="")
            row = df[df["bond_id"] == symbol]
            if len(row) == 0:
                return None
            r = row.iloc[0]
            price = float(r.get("price", 0) or 0)
            if price <= 0:
                return None
            # Construct minimal daily frame from snapshot
            today = pd.Timestamp.now().strftime("%Y-%m-%d")
            result = pd.DataFrame({
                "date": [today], "close": [price],
                "convert_premium": [float(r.get("convert_premium_ratio", 0) or 0)],
                "ytm": [float(r.get("ytm_rt", 0) or 0)],
            })
            result["date"] = pd.to_datetime(result["date"])
            result = result.set_index("date")
            return result
        except Exception:
            return None

    def fetch_fundamentals(self, symbol: str) -> Dict:
        """Bond fundamentals: yield, duration, spread."""
        if symbol in YIELD_COLUMNS:
            df = self._load_yields()
            if df is None or YIELD_COLUMNS[symbol] not in df.columns:
                return {}
            latest = df.iloc[-1]
            y10 = latest.get("中国国债收益率10年", 0)
            y2 = latest.get("中国国债收益率2年", 0)
            return {
                "yield_10y": float(y10 or 0),
                "yield_2y": float(y2 or 0),
                "spread_10y2y": float((y10 or 0) - (y2 or 0)),
                "yield_curve": "normal" if (y10 or 0) > (y2 or 0) else "inverted",
            }
        return {}

    def get_universe(self) -> List[str]:
        return self._universe

    def get_metadata(self, symbol: str) -> Dict:
        name = BOND_NAMES.get(symbol, symbol)
        category = "treasury" if symbol.startswith("CN") else "convertible"
        return {
            "name": name, "industry": category,
            "sector": category, "asset_type": "bond",
        }

    def __repr__(self) -> str:
        return f"<BondAsset: {len(self._universe)} bonds>"
