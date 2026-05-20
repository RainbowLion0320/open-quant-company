"""
宏观经济指标数据获取器 — Tushare 优先 (CPI/PPI/PMI) + AKShare 兜底

数据源:
  Tushare cn_cpi/cn_ppi/cn_pmi — 国家统计局, 月频, 最新到上月
  AKShare — 金十数据 (已停更, 仅作历史回退)
  AKShare — 央行 (money_supply, shibor, lpr 仍正常)

缓存: data/store/macro/{indicator}.parquet
"""

import time
import os
import re
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
    },
    "pmi": {
        "api": "macro_china_pmi_yearly",
        "tushare_api": "cn_pmi",
        "label": "制造业PMI",
        "freq": "monthly",
    },
    "cpi": {
        "api": "macro_china_cpi_yearly",
        "tushare_api": "cn_cpi",
        "label": "居民消费价格指数CPI",
        "freq": "monthly",
    },
    "ppi": {
        "api": "macro_china_ppi_yearly",
        "tushare_api": "cn_ppi",
        "label": "工业生产者出厂价格PPI",
        "freq": "monthly",
    },
    "gdp": {
        "api": "macro_china_gdp_yearly",
        "tushare_api": "cn_gdp",
        "label": "国内生产总值GDP",
        "freq": "quarterly",
    },
    "shibor": {
        "api": "macro_china_shibor_all",
        "label": "Shibor利率",
        "freq": "daily",
    },
    "lpr": {
        "api": "macro_china_lpr",
        "tushare_api": "shibor_lpr",
        "label": "LPR贷款基础利率",
        "freq": "monthly",
    },
}


def _quarter_to_date(value) -> pd.Timestamp:
    """Convert Tushare quarter labels such as 2025Q4/20254 to quarter-end date."""
    text = str(value).strip().upper()
    match = re.match(r"^(\d{4})Q([1-4])$", text)
    if not match:
        match = re.match(r"^(\d{4})([1-4])$", text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2)) * 3
        return pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return pd.NaT
    return parsed


class MacroFetcher:
    """宏观经济数据获取器 (Tushare优先, AKShare兜底)"""

    def __init__(self):
        self.store_dir = HUB.store_dir("macro")
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _tushare_fetch(self, api_name: str, **params) -> Optional[pd.DataFrame]:
        """Call Tushare HTTP API directly, return DataFrame or None."""
        import requests as _r
        from data.tushare_utils import get_tushare_token
        token = get_tushare_token()
        if not token:
            return None
        try:
            resp = _r.post("http://api.tushare.pro", json={
                "api_name": api_name,
                "token": token,
                "params": params,
                "fields": "",  # all fields
            }, timeout=30)
            data = resp.json()
            items = data.get("data", {}).get("items", [])
            fields = data.get("data", {}).get("fields", [])
            if not items or not fields:
                return None
            df = pd.DataFrame(items, columns=fields)
            return df
        except Exception:
            return None

    def fetch_indicator(self, name: str, force: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetch one macro indicator.
        Tushare priority for CPI/PPI/PMI; AKShare fallback.
        Caches to Parquet.
        """
        if name not in MACRO_INDICATORS:
            print(f"  [macro] Unknown indicator: {name}")
            return None

        cache_path = HUB.macro_path(name)
        if cache_path.exists() and not force:
            try:
                return HUB.read_parquet(cache_path)
            except Exception:
                pass
        elif cache_path.exists() and force:
            cache_path.unlink(missing_ok=True)  # force: delete old cache, refetch

        info = MACRO_INDICATORS[name]

        # ── Tushare path (CPI/PPI/PMI) ──
        tushare_api = info.get("tushare_api")
        if tushare_api:
            # Try Tushare first for fresh data
            try:
                time.sleep(0.3)
                df = self._tushare_fetch(tushare_api)
                if df is not None and len(df) > 0:
                    df = self._normalize(name, df, source="tushare")
                    HUB.write_parquet(df, cache_path)
                    return df
            except Exception as e:
                print(f"  [macro] Tushare {name}: {type(e).__name__}: {str(e)[:60]}")

        # ── AKShare fallback ──
        try:
            time.sleep(0.5)
            import akshare as ak
            fn: Callable = getattr(ak, info["api"])
            raw = fn()
            if raw is None or len(raw) == 0:
                return None
            df = self._normalize(name, raw, source="akshare")
            HUB.write_parquet(df, cache_path)
            return df
        except Exception as e:
            print(f"  [macro] {name}: {type(e).__name__}: {str(e)[:80]}")
            return None

    def _normalize(self, name: str, raw: pd.DataFrame, source: str = "akshare") -> pd.DataFrame:
        """Normalize raw output to standard column names."""

        if name == "money_supply":
            if source == "akshare":
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
            if source == "tushare":
                # Tushare returns UPPERCASE fields: MONTH, PMI010000, etc.
                date_col = "MONTH" if "MONTH" in raw.columns else "month"
                pmi_col = "PMI010000" if "PMI010000" in raw.columns else "pmi010000"
                raw = raw.rename(columns={date_col: "date", pmi_col: "pmi_mfg"})
                raw["date"] = pd.to_datetime(raw["date"].astype(str) + "01", format="%Y%m%d", errors="coerce")
                for c in raw.columns:
                    if c not in ("date",):
                        raw[c] = pd.to_numeric(raw[c], errors="coerce")
                return raw.sort_values("date").reset_index(drop=True)
            # AKShare
            raw = raw.rename(columns={"日期": "date", "制造业-官方": "pmi_mfg"})
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        if name == "cpi":
            if source == "tushare":
                # Tushare fields might be UPPERCASE: MONTH, NT_VAL, NT_YOY, etc.
                date_col = "MONTH" if "MONTH" in raw.columns else "month"
                raw = raw.rename(columns={
                    date_col: "date",
                    **{c: c.lower() for c in raw.columns if c != date_col},
                })
                raw["date"] = pd.to_datetime(raw["date"].astype(str) + "01", format="%Y%m%d", errors="coerce")
                for c in raw.columns:
                    if c not in ("date",):
                        raw[c] = pd.to_numeric(raw[c], errors="coerce")
                return raw.sort_values("date").reset_index(drop=True)
            # AKShare fallback
            raw = raw.rename(columns={c: c.replace("日期", "date") for c in raw.columns})
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        if name == "ppi":
            if source == "tushare":
                date_col = "MONTH" if "MONTH" in raw.columns else "month"
                raw = raw.rename(columns={
                    date_col: "date",
                    **{c: c.lower() for c in raw.columns if c != date_col},
                })
                raw["date"] = pd.to_datetime(raw["date"].astype(str) + "01", format="%Y%m%d", errors="coerce")
                for c in raw.columns:
                    if c not in ("date",):
                        raw[c] = pd.to_numeric(raw[c], errors="coerce")
                return raw.sort_values("date").reset_index(drop=True)
            # AKShare fallback
            raw = raw.rename(columns={c: c.replace("日期", "date") for c in raw.columns})
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        if name == "gdp":
            if source == "tushare":
                quarter_col = "QUARTER" if "QUARTER" in raw.columns else "quarter"
                raw = raw.rename(columns={
                    quarter_col: "quarter",
                    "gdp": "gdp",
                    "gdp_yoy": "gdp_yoy",
                    "pi": "pi", "pi_yoy": "pi_yoy",
                    "si": "si", "si_yoy": "si_yoy",
                    "ti": "ti", "ti_yoy": "ti_yoy",
                })
                raw = raw.rename(columns={c: c.lower() for c in raw.columns if c != "quarter"})
                raw["date"] = raw["quarter"].map(_quarter_to_date)
                for c in raw.columns:
                    if c not in ("quarter", "date"):
                        raw[c] = pd.to_numeric(raw[c], errors="coerce")
                return raw.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
            # AKShare fallback
            raw = raw.rename(columns={c: c.replace("日期", "date") for c in raw.columns})
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        if name == "shibor":
            raw = raw.rename(columns={
                "日期": "date",
                "O/N-定价": "ON", "1W-定价": "1W", "2W-定价": "2W",
                "1M-定价": "1M", "3M-定价": "3M", "6M-定价": "6M",
                "9M-定价": "9M", "1Y-定价": "1Y",
            })
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        if name == "lpr":
            if source == "tushare":
                # Tushare shibor_lpr: date (YYYYMMDD), 1y, 5y
                date_col = next((c for c in raw.columns if str(c).lower() == "date"), "date")
                one_y_col = next((c for c in raw.columns if str(c).lower() == "1y"), "1y")
                five_y_col = next((c for c in raw.columns if str(c).lower() == "5y"), "5y")
                raw = raw.rename(columns={
                    date_col: "date", one_y_col: "LPR_1Y", five_y_col: "LPR_5Y",
                })
                raw["date"] = pd.to_datetime(raw["date"].astype(str), format="%Y%m%d", errors="coerce")
                for c in raw.columns:
                    if c not in ("date",):
                        raw[c] = pd.to_numeric(raw[c], errors="coerce")
                # Keep only rows where LPR changed (monthly cadence)
                raw = raw.dropna(subset=["LPR_1Y"])
                return raw.sort_values("date").reset_index(drop=True)
            # AKShare fallback
            raw = raw.rename(columns={"TRADE_DATE": "date", "LPR1Y": "LPR_1Y", "LPR5Y": "LPR_5Y"})
            raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
            return raw

        return raw

    def fetch_all(self, force: bool = False) -> Dict[str, pd.DataFrame]:
        """Fetch all macro indicators."""
        results = {}
        for name in MACRO_INDICATORS:
            print(f"  [macro] Fetching {MACRO_INDICATORS[name]['label']}...")
            df = self.fetch_indicator(name, force=force)
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
            # Tushare format: nt_yoy (Natl Total YoY); AKShare: columns with "同比"
            if "nt_yoy" in latest.index:
                factors["macro_cpi_yoy"] = float(latest.get("nt_yoy", 0) or 0)
            elif "cpi_yoy" in latest.index:
                factors["macro_cpi_yoy"] = float(latest.get("cpi_yoy", 0) or 0)
            else:
                for c in latest.index:
                    if "同比" in str(c):
                        factors["macro_cpi_yoy"] = float(latest[c] or 0)
                        break

        if name == "ppi":
            if "ppi_yoy" in latest.index:
                factors["macro_ppi_yoy"] = float(latest.get("ppi_yoy", 0) or 0)

        if name == "gdp":
            if "gdp_yoy" in latest.index:
                factors["macro_gdp_yoy"] = float(latest.get("gdp_yoy", 0) or 0)

        if name == "shibor":
            factors["macro_shibor_on"] = float(latest.get("ON", 0) or 0)
            factors["macro_shibor_3m"] = float(latest.get("3M", 0) or 0)

        if name == "lpr":
            factors["macro_lpr_1y"] = float(latest.get("LPR_1Y", 0) or 0)
            factors["macro_lpr_5y"] = float(latest.get("LPR_5Y", 0) or 0)

    return factors
