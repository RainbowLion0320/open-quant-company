"""
Stock Asset Adapter — A-share equities

Wraps existing data modules (fetcher.py, financials.py, symbols.py)
into the uniform AssetAdapter interface.

All data fetched from AKShare + Tushare MCP, cached in Parquet.
"""
from typing import Dict, List, Optional

import pandas as pd

from data.assets.base import AssetAdapter
from data.fetcher import get_stock_daily
from data.financials import _parse_pct, _parse_financial_number
from data.symbols import CIRCLE_STOCKS, SYMBOL_NAME, SYMBOL_INDUSTRY, SYMBOL_SECTOR
from data.symbol_utils import to_ts_code
from data.tushare_utils import get_tushare_token


class StockAsset(AssetAdapter):
    """A-share stock adapter."""

    asset_type = "stock"
    label = "A股股票"
    description = "沪深A股，1000只股票池，申万31行业分类"
    DATA_SOURCE = "real"
    DATA_SOURCE_DETAIL = "AKShare + Tushare OHLCV (新浪/东方财富/腾讯3源fallback)"
    TRADING_CALENDAR = "SSE"

    def fetch_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> Optional[pd.DataFrame]:
        """Fetch daily OHLCV via AKShare (cached to Parquet)."""
        return get_stock_daily(symbol)

    def get_universe(self) -> List[str]:
        """Return the full stock pool (1000 symbols)."""
        return list(CIRCLE_STOCKS)

    def get_metadata(self, symbol: str) -> Dict:
        """Return metadata: name, industry, area, market."""
        return {
            "symbol": symbol,
            "name": SYMBOL_NAME.get(symbol, ""),
            "industry": SYMBOL_INDUSTRY.get(symbol, ""),
            "sector": SYMBOL_SECTOR.get(symbol, ""),
        }

    def fetch_fundamentals(self, symbol: str) -> Dict:
        """Fetch financial summary via 同花顺 (cached 3-tier)."""
        from data.financials import get_financial_summary
        df = get_financial_summary(symbol)
        if df is None or len(df) == 0:
            return {}
        latest = df.iloc[-1]
        return {
            "roe": _parse_pct(latest.get("净资产收益率", 0)),
            "gross_margin": _parse_pct(latest.get("销售毛利率", 0)),
            "net_margin": _parse_pct(latest.get("销售净利率", 0)),
            "debt_equity": _parse_pct(latest.get("产权比率", 0)),
            "net_profit": _parse_financial_number(str(latest.get("净利润", 0))),
            "revenue": _parse_financial_number(str(latest.get("营业总收入", 0))),
        }

    def fetch_valuation(self, symbol: str, date: Optional[str] = None) -> Dict:
        """Fetch PE/PB/PS/market cap via Tushare daily_basic."""
        import time
        import tushare as ts

        token = get_tushare_token()
        if not token:
            return {}

        ts_code = to_ts_code(symbol)
        if not ts_code:
            return {}

        try:
            api = ts.pro_api(token)
            time.sleep(0.3)
            if date:
                df = api.daily_basic(ts_code=ts_code, trade_date=date.replace("-", ""))
            else:
                df = api.daily_basic(ts_code=ts_code)

            if df is None or len(df) == 0:
                return {}
            row = df.iloc[-1]
            return {
                "pe_ttm": float(row.get("pe_ttm", 0) or 0),
                "pb": float(row.get("pb", 0) or 0),
                "ps_ttm": float(row.get("ps_ttm", 0) or 0),
                "dv_ratio": float(row.get("dv_ratio", 0) or 0),
                "total_mv": float(row.get("total_mv", 0) or 0),
                "circ_mv": float(row.get("circ_mv", 0) or 0),
                "turnover_rate": float(row.get("turnover_rate", 0) or 0),
                "volume_ratio": float(row.get("volume_ratio", 0) or 0),
            }
        except Exception:
            return {}

    def fetch_shareholder_count(self, symbol: str) -> Optional[Dict]:
        """Fetch latest shareholder data via AKShare (free)."""
        from data.fetchers.holders import HolderFetcher
        hf = HolderFetcher()
        return hf.get_latest(symbol)

    def fetch_moneyflow(self, symbol: str) -> Dict:
        """Fetch latest moneyflow via AKShare (free)."""
        from data.fetchers.moneyflow import MoneyflowFetcher
        mf = MoneyflowFetcher()
        return mf.get_latest(symbol)
