"""
ETF Asset Adapter — 多资产架构第二实现

数据源:
  - AKShare fund_etf_spot_em (实时行情, 1466只)
  - AKShare fund_etf_hist_em (历史OHLCV)
  - 分类: 宽基/行业/债券/黄金/跨境 QDII

因子:
  - 折溢价率: (最新价-IOPV)/IOPV
  - 规模增长: 最新份额 vs 20日前
  - 资金流向: 主力净流入/占比
  - 换手率: 流动性指标
"""
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import time
from pathlib import Path

from data.assets.base import AssetAdapter
from data.datahub import get_datahub

HUB = get_datahub()


# ── ETF universe: top 200 by volume + category diversity ──
# Selected from AKShare fund_etf_spot_em, covering major categories
ETF_UNIVERSE = [
    # 宽基指数 (equity broad)
    "510050", "510300", "510500", "510880", "510310", "510330",
    "512100", "512500", "515050", "515790", "588000", "588080",
    "159915", "159919", "159922", "159949", "159845",
    # 行业主题 (equity sector)
    "512880", "512800", "512760", "512070", "512690", "512710",
    "515700", "516160", "159995", "159996", "159766", "159857",
    # 债券 (bond)
    "511010", "511260", "511220", "511030", "511090",
    # 黄金/商品 (commodity)
    "518880", "518680", "159937", "159980", "159981",
    # 跨境 QDII
    "513100", "513500", "513050", "513330", "513060",
    "159612", "159632", "159696", "159941",
    # 货币/短债 (cash equivalent)
    "511880", "511660", "511920",
]

ETF_NAME_CACHE: Dict[str, str] = {}
ETF_CATEGORY_CACHE: Dict[str, str] = {}

# Category mapping based on code prefix / known classifications
def _classify_etf(code: str, name: str = "") -> str:
    """Classify ETF into category based on code and name patterns."""
    name_lower = name.lower() if name else ""
    code = str(code)

    # Bond ETFs
    if any(kw in name for kw in ["债", "国债", "城投", "地债", "转债"]):
        return "bond"
    # Gold / Commodity
    if any(kw in name for kw in ["黄金", "金", "有色", "商品", "原油", "油气", "豆粕"]):
        return "commodity"
    # Cross-border QDII
    if any(kw in name for kw in ["纳指", "标普", "恒生", "港股", "港股通", "日经", "德国", "法国", "印度"]):
        return "qdi"
    # Money market
    if any(kw in name for kw in ["货币", "添益", "理财"]):
        return "cash"

    # By code prefix
    if code.startswith("511"):
        if code in ("511880", "511660", "511920"):
            return "cash"
        return "bond"
    if code.startswith("518"):
        return "commodity"
    if code.startswith("513"):
        return "qdi"
    if code.startswith("1596") or code.startswith("1599"):
        if "跨境" in name or "QD" in name.upper():
            return "qdi"

    # Default
    if code.startswith(("510", "512", "515", "516", "588", "159")):
        return "equity"

    return "equity"


class ETFAsset(AssetAdapter):
    """ETF asset adapter: OHLCV + fundamentals + flows."""

    asset_type: str = "etf"
    label: str = "ETF基金"
    description: str = "A股场内ETF (宽基/行业/债券/黄金/跨境)"
    DATA_SOURCE: str = "real"
    DATA_SOURCE_DETAIL: str = "AKShare fund_etf_hist_em (日线OHLCV) + fund_etf_spot_em (实时行情)"
    TRADING_CALENDAR: str = "SSE"

    def __init__(self, store_root: Path | str | None = None):
        super().__init__(store_root)
        self._universe = list(ETF_UNIVERSE)
        self._universe_dir = self.asset_dir / "universe"
        self._universe_dir.mkdir(parents=True, exist_ok=True)

    # ── Core Interface ──

    def fetch_daily(
        self, symbol: str, start_date: str = "20180101", end_date: str = "",
    ) -> Optional[pd.DataFrame]:
        """Fetch OHLCV via AKShare fund_etf_hist_em."""
        import os
        for k in list(os.environ.keys()):
            if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
                del os.environ[k]
        os.environ.setdefault('no_proxy', '*')

        cache_path = self.cache_path(symbol)
        if cache_path.exists():
            try:
                cached = HUB.read_parquet(cache_path)
                if len(cached) > 0:
                    cached["date"] = pd.to_datetime(cached["date"])
                    return cached
            except Exception:
                pass

        try:
            import akshare as ak
            time.sleep(0.5)
            end = end_date or pd.Timestamp.now().strftime("%Y%m%d")
            df = ak.fund_etf_hist_em(symbol=symbol, period="daily",
                                     start_date=start_date, end_date=end)
            if df is None or len(df) == 0:
                return None

            df = df.rename(columns={
                "日期": "date", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume",
                "成交额": "amount",
            })
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
            HUB.write_parquet(df, cache_path)
            return df
        except Exception as e:
            print(f"  [ETF] {symbol}: {type(e).__name__}: {str(e)[:60]}")
            return None

    def fetch_fundamentals(self, symbol: str) -> Dict:
        """Fetch ETF-specific fundamentals: discount/premium, size growth, flows."""
        # Use global cache to avoid re-downloading 1466 ETFs each call
        if not hasattr(ETFAsset, '_spot_cache'):
            try:
                import akshare as ak
                import os as _os
                for k in list(_os.environ.keys()):
                    if k.lower() in ('http_proxy', 'https_proxy', 'all_proxy'):
                        del _os.environ[k]
                _os.environ.setdefault('no_proxy', '*')
                ETFAsset._spot_cache = ak.fund_etf_spot_em()
            except Exception:
                ETFAsset._spot_cache = None

        if ETFAsset._spot_cache is None:
            return {}
        df = ETFAsset._spot_cache
        try:
            row = df[df["代码"] == symbol]
            if len(row) == 0:
                return {}
            r = row.iloc[0]

            # 折溢价率
            discount = float(r.get("基金折价率", 0) or 0) / 100.0
            # 规模 (亿份)
            shares = float(r.get("最新份额", 0) or 0)
            # 成交额 (亿元)
            amount = float(r.get("成交额", 0) or 0)
            # 换手率
            turnover = float(r.get("换手率", 0) or 0)
            # 主力净流入
            main_flow = float(r.get("主力净流入-净额", 0) or 0)
            main_flow_pct = float(r.get("主力净流入-净占比", 0) or 0) / 100.0

            # Cache name & category
            name = str(r.get("名称", ""))
            ETF_NAME_CACHE[symbol] = name
            ETF_CATEGORY_CACHE[symbol] = _classify_etf(symbol, name)

            return {
                "discount_rate": discount,     # 折溢价 (-1 = 折价1%)
                "shares": shares,               # 最新份额(亿份)
                "amount": amount,               # 成交额(亿元)
                "turnover_rate": turnover,      # 换手率%
                "main_flow_net": main_flow,     # 主力净流入(元)
                "main_flow_pct": main_flow_pct, # 主力净流入占比
            }
        except Exception as e:
            print(f"  [ETF-fund] {symbol}: {type(e).__name__}: {str(e)[:40]}")
            return {}

    def get_universe(self) -> List[str]:
        return self._universe

    def get_metadata(self, symbol: str) -> Dict:
        """Return name and category."""
        name = ETF_NAME_CACHE.get(symbol, "")
        category = ETF_CATEGORY_CACHE.get(symbol, "")
        if not name:
            # Try to fetch
            self.fetch_fundamentals(symbol)
            name = ETF_NAME_CACHE.get(symbol, symbol)
            category = ETF_CATEGORY_CACHE.get(symbol, _classify_etf(symbol))
        return {
            "name": name or symbol,
            "industry": category or "equity",
            "sector": category or "equity",
            "asset_type": "etf",
        }

    # ── ETF-specific factor data ──

    def fetch_factor_data(
        self, symbol: str, factor_name: str, date: Optional[str] = None
    ) -> Optional[float]:
        """Fetch specific factor: discount_rate, size_growth, flow_strength."""
        fund = self.fetch_fundamentals(symbol)
        if not fund:
            return None

        if factor_name == "discount_rate":
            return fund.get("discount_rate")
        if factor_name == "shares":
            return fund.get("shares")
        if factor_name == "turnover_rate":
            return fund.get("turnover_rate")
        if factor_name == "main_flow_pct":
            return fund.get("main_flow_pct")
        return None

    def __repr__(self) -> str:
        return f"<ETFAsset: {len(self._universe)} ETFs>"
