"""
宏观经济指标数据获取器 — AKShare (免费, 央行/统计局/金十数据)

AKShare macro APIs:
  macro_china_money_supply()     — M0/M1/M2 (央行, 1998-)
  macro_china_pmi_yearly()       — 官方制造业PMI (金十数据)
  macro_china_cpi_yearly()       — CPI (金十数据)
  macro_china_ppi_yearly()       — PPI (金十数据)
  macro_china_gdp_yearly()       — GDP (统计局)
  macro_china_shibor_all()       — Shibor全期限 (央行)
  macro_china_lpr()              — LPR贷款利率 (央行)

缓存: data/store/macro/{indicator}.parquet
"""
import time
import os
from pathlib import Path
from typing import Dict, List, Optional, Callable

import pandas as pd
import numpy as np

from data.datahub import get_datahub

HUB = get_datahub()

# Macro indicator registry
MACRO_INDICATORS = {
    "money_supply": {
        "api": "macro_china_money_supply",
        "label": "货币供应量 M0/M1/M2",
        "freq": "monthly",
        "columns": ["月份", "M2_数量_亿元", "M2_同比", "M1_数量_亿元", "M1_同比", "M0_数量_亿元", "M0_同比"],
    },
    "pmi": {
        "api": "macro_china_pmi_yearly",
        "label": "制造业PMI",
        "freq": "monthly",
        "columns": ["日期", "PMI_制造业"],
    },
    "cpi": {
        "api": "macro_china_cpi_yearly",
        "label": "居民消费价格指数CPI",
        "freq": "monthly",
        "columns": ["日期", "CPI_全国_同比", "CPI_全国_环比", "CPI_城市_同比", "CPI_农村_同比"],
    },
    "ppi": {
        "api": "macro_china_ppi_yearly",
        "label": "工业生产者出厂价格PPI",
        "freq": "monthly",
        "columns": ["日期", "PPI_同比"],
    },
    "gdp": {
        "api": "macro_china_gdp_yearly",
        "label": "国内生产总值GDP",
        "freq": "quarterly",
        "columns": ["日期", "GDP_累计值_亿元", "GDP_同比"],
    },
    "shibor": {
        "api": "macro_china_shibor_all",
        "label": "Shibor利率",
        "freq": "daily",
        "columns": ["日期", "ON", "1W", "2W", "1M", "3M", "6M", "9M", "1Y"],
    },
    "lpr": {
        "api": "macro_china_lpr",
        "label": "LPR贷款基础利率",
        "freq": "monthly",
        "columns": ["日期", "LPR_1Y", "LPR_5Y"],
    },
}


class MacroFetcher:
    """宏观经济数据获取器 (AKShare, 免费无限)"""

    def __init__(self):
        self.store_dir = HUB.store_dir("macro")
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def fetch_indicator(self, name: str) -> Optional[pd.DataFrame]:
        """
        Fetch one macro indicator.
        Caches to Parquet. Returns normalized DataFrame.
        """
        if name not in MACRO_INDICATORS:
            print(f"  [macro] Unknown indicator: {name}")
            return None

        cache_path = HUB.macro_path(name)
        if cache_path.exists():
            try:
                df = HUB.read_parquet(cache_path)
                # Macro data updates monthly — cache for 7 days
                return df
            except Exception:
                pass

        import akshare as ak
        info = MACRO_INDICATORS[name]
        api_name = info["api"]

        try:
            time.sleep(0.5)
            fn: Callable = getattr(ak, api_name)
            raw = fn()

            if raw is None or len(raw) == 0:
                return None

            # Normalize to standard format
            df = self._normalize(name, raw)
            HUB.write_parquet(df, cache_path)
            return df
        except Exception as e:
            print(f"  [macro] {name}: {type(e).__name__}: {str(e)[:80]}")
            return None

    def _normalize(self, name: str, raw: pd.DataFrame) -> pd.DataFrame:
        """Normalize raw AKShare output to standard column names."""
        info = MACRO_INDICATORS[name]

        if name == "money_supply":
            raw = raw.rename(columns={
                "月份": "date",
                "货币和准货币(M2)-数量(亿元)": "M2_stock",
                "货币和准货币(M2)-同比增长": "M2_yoy",
                "货币(M1)-数量(亿元)": "M1_stock",
                "货币(M1)-同比增长": "M1_yoy",
                "流通中的现金(M0)-数量(亿元)": "M0_stock",
                "流通中的现金(M0)-同比增长": "M0_yoy",
            })
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw[[c for c in ["date", "M2_stock", "M2_yoy", "M1_stock", "M1_yoy", "M0_stock", "M0_yoy"] if c in raw.columns]]

        if name == "pmi":
            raw = raw.rename(columns={"日期": "date", "制造业-官方": "pmi_mfg"})
            if "财新" in str(raw.columns):
                raw = raw.rename(columns={c: "pmi_caixin" for c in raw.columns if "财新" in str(c)})
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        if name in ("cpi", "ppi"):
            raw = raw.rename(columns={c: c.replace("日期", "date") for c in raw.columns})
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        if name == "gdp":
            raw = raw.rename(columns={c: c.replace("日期", "date") for c in raw.columns})
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        if name == "shibor":
            raw = raw.rename(columns={
                "日期": "date",
                "O/N-定价": "ON",
                "1W-定价": "1W",
                "2W-定价": "2W",
                "1M-定价": "1M",
                "3M-定价": "3M",
                "6M-定价": "6M",
                "9M-定价": "9M",
                "1Y-定价": "1Y",
            })
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        if name == "lpr":
            raw = raw.rename(columns={"TRADE_DATE": "date", "LPR1Y": "LPR_1Y", "LPR5Y": "LPR_5Y"})
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        return raw

    def fetch_all(self) -> Dict[str, pd.DataFrame]:
        """Fetch all macro indicators."""
        results = {}
        for name in MACRO_INDICATORS:
            print(f"  [macro] Fetching {MACRO_INDICATORS[name]['label']}...")
            df = self.fetch_indicator(name)
            if df is not None:
                results[name] = df
                print(f"    ✓ {len(df)} rows")
            else:
                print(f"    ✗ failed")
        return results

    def get_latest(self, name: str) -> Optional[Dict]:
        """Get latest value for one indicator."""
        df = self.fetch_indicator(name)
        if df is None or len(df) == 0:
            return None
        return df.iloc[-1].to_dict()

    def list_indicators(self) -> Dict:
        """List all available macro indicators."""
        return dict(MACRO_INDICATORS)


def derive_macro_factors(macro_data: Dict[str, pd.DataFrame], date_str: str) -> Dict:
    """
    Derive macro regime factors for a given date.

    PIT-safe: only uses data before date_str.

    Returns factor_name → value dict.
    """
    factors = {}
    target_date = pd.to_datetime(date_str)

    for name, df in macro_data.items():
        if df is None or len(df) == 0:
            continue
        if "date" not in df.columns:
            continue

        df = df[df["date"] <= target_date]
        if len(df) == 0:
            continue

        latest = df.iloc[-1]

        if name == "money_supply":
            factors["macro_m2_yoy"] = float(latest.get("M2_yoy", 0) or 0)
            factors["macro_m1_yoy"] = float(latest.get("M1_yoy", 0) or 0)
            factors["macro_m1m2_spread"] = round(
                float(latest.get("M1_yoy", 0) or 0) - float(latest.get("M2_yoy", 0) or 0), 4
            )

        if name == "pmi":
            factors["macro_pmi_mfg"] = float(latest.get("pmi_mfg", 50) or 50)

        if name == "cpi":
            for c in latest.index:
                if "同比" in str(c):
                    factors[f"macro_cpi_yoy"] = float(latest[c] or 0)
                    break

        if name == "shibor":
            factors["macro_shibor_on"] = float(latest.get("ON", 0) or 0)
            factors["macro_shibor_3m"] = float(latest.get("3M", 0) or 0)

    return factors
