"""
财务数据桥接层 — 从 AKShare 提取 ROE/毛利率/负债率，驱动巴菲特过滤器
数据源：同花顺 (stock_financial_abstract_ths)
"""
from typing import Tuple, List, Optional
import pandas as pd
import numpy as np
import os

from core.settings import get_settings
from data.storage.datahub import get_datahub
from data.ingestion.fetcher import retry_with_backoff

# ---- 配置加载 ----
_CONFIG = None

def _load_config():
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    try:
        _CONFIG = get_settings()
    except Exception:
        _CONFIG = {}
    return _CONFIG

# 模块级常量，从 config 读取，不可用时回退到合理默认值
_MIN_ROE_YEARS = 5
_FCF_FALLBACK_RATIO = 0.7
_GROWTH_MIN = 0.03
_GROWTH_MAX = 0.12
_GROWTH_DEFAULT = 0.05

try:
    _cfg = _load_config()
    _buffett = _cfg.get("buffett", {})
    _MIN_ROE_YEARS = _buffett.get("moat", {}).get("min_roe_years", _MIN_ROE_YEARS)
    _valuation = _buffett.get("valuation", {})
    _FCF_FALLBACK_RATIO = _valuation.get("fcf_fallback_ratio", _FCF_FALLBACK_RATIO)
    _GROWTH_MIN = _valuation.get("growth_min", _GROWTH_MIN)
    _GROWTH_MAX = _valuation.get("growth_max", _GROWTH_MAX)
    _GROWTH_DEFAULT = _valuation.get("growth_default", _GROWTH_DEFAULT)
except Exception:
    pass

# ---- 内存缓存 + 磁盘缓存 ----
_financial_cache: dict = {}
_FINANCIAL_CACHE_MAX_SIZE = 50  # LRU上限，防止OOM

import os as _os
import gc as _gc
_HUB = get_datahub()
_CACHE_DIR = _HUB.stock_data_dir("financials")


def _evict_lru():
    """当缓存超过上限时，淘汰最老的一半条目"""
    if len(_financial_cache) <= _FINANCIAL_CACHE_MAX_SIZE:
        return
    # 只保留最近的一半
    to_keep = _FINANCIAL_CACHE_MAX_SIZE // 2
    keys = list(_financial_cache.keys())
    for key in keys[:-to_keep]:
        del _financial_cache[key]
    _gc.collect()


def _parse_pct(val) -> float:
    """解析百分比字符串 '54.27%' → 0.5427, 纯数字按百分比处理"""
    if val is None or val == "False" or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        v = float(val)
        if pd.isna(v):
            return 0.0
        return v / 100 if abs(v) > 1 else v
    if isinstance(val, str):
        has_pct = "%" in val
        val = val.replace("%", "").replace(",", "")
        try:
            f = float(val)
            if has_pct:
                return f / 100
            return f / 100 if abs(f) > 1 else f
        except ValueError:
            return 0.0
    return 0.0


def _get_cache_path(symbol: str) -> str:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return str(_CACHE_DIR / f"{symbol}.parquet")


@retry_with_backoff(max_retries=2, base_delay=2.0)
def get_financial_summary(symbol: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    获取个股财务摘要（同花顺源 → 本地 parquet）。

    默认只读本地 Parquet；外部 API 拉取只在 force_refresh=True 或
    QUANT_ALLOW_API_FALLBACK=1 时发生。
    """
    from data.ingestion.fetchers.financial import read_financial_summary, fetch_financial_summary

    if not force_refresh:
        df = read_financial_summary(symbol)
        if df is not None and len(df) > 0:
            return df
        if os.environ.get("QUANT_ALLOW_API_FALLBACK", "").lower() not in {"1", "true", "yes", "on"}:
            return pd.DataFrame()

    df = fetch_financial_summary(symbol)
    if df is not None and len(df) > 0:
        return df
    return pd.DataFrame()


def extract_roe_history(df: pd.DataFrame, years: int = None) -> List[float]:
    """
    从财务摘要 DataFrame 提取近N年 ROE 序列（仅取年报）
    返回: [ROE_year1, ROE_year2, ...] 从旧到新排列
    """
    if years is None:
        years = _MIN_ROE_YEARS
    if "净资产收益率" not in df.columns:
        return []

    # 只取年报（报告期以 -12-31 结尾）
    report_col = "报告期"
    annual = df[df[report_col].astype(str).str.endswith("-12-31")].copy()
    if len(annual) == 0:
        annual = df.copy()

    annual = annual.sort_values(report_col)
    roe_values = annual["净资产收益率"].apply(_parse_pct).tolist()
    return roe_values[-years:] if len(roe_values) > years else roe_values


def extract_gross_margin_history(df: pd.DataFrame, years: int = None) -> List[float]:
    """
    从财务摘要提取近N年毛利率序列（仅取年报）
    """
    if years is None:
        years = _MIN_ROE_YEARS
    if "销售毛利率" not in df.columns:
        return []

    report_col = "报告期"
    annual = df[df[report_col].astype(str).str.endswith("-12-31")].copy()
    if len(annual) == 0:
        annual = df.copy()

    annual = annual.sort_values(report_col)
    gm_values = annual["销售毛利率"].apply(_parse_pct).tolist()
    return gm_values[-years:] if len(gm_values) > years else gm_values


def extract_debt_equity_ratio(df: pd.DataFrame) -> float:
    """
    从财务摘要提取最新负债权益比（D/E ratio）
    优先使用 产权比率 列（直接就是 D/E），回退到 资产负债率 换算
    """
    if df is None or len(df) == 0:
        return 0.0
    report_col = "报告期"
    has_report_col = report_col in df.columns

    # 优先：产权比率 直接就是 D/E
    if "产权比率" in df.columns:
        # 取最新年报的产权比率
        if has_report_col:
            annual = df[df[report_col].astype(str).str.endswith("-12-31")]
        else:
            annual = df.copy()
        if len(annual) == 0:
            annual = df
        if has_report_col:
            latest = annual.sort_values(report_col).iloc[-1]
        else:
            latest = annual.iloc[-1]
        val = latest["产权比率"]
        try:
            f = float(val)
            return f if f > 0 else 0.0
        except (ValueError, TypeError):
            return 0.0

    # 回退：资产负债率 → D/E = debt_ratio / (1 - debt_ratio)
    if "资产负债率" not in df.columns:
        return 0.0

    if has_report_col:
        latest = df.sort_values(report_col).iloc[-1]
    else:
        latest = df.iloc[-1]
    debt_ratio = _parse_pct(latest["资产负债率"])
    if debt_ratio >= 1.0:
        return 99.0  # 极端情况
    return debt_ratio / (1 - debt_ratio) if debt_ratio < 1 else 99.0


def extract_net_margin_history(df: pd.DataFrame, years: int = None) -> List[float]:
    """
    从财务摘要提取近N年销售净利率序列（仅取年报）
    用于金融板块替代毛利率
    """
    if years is None:
        years = _MIN_ROE_YEARS
    if "销售净利率" not in df.columns:
        return []

    report_col = "报告期"
    annual = df[df[report_col].astype(str).str.endswith("-12-31")].copy()
    if len(annual) == 0:
        annual = df.copy()

    annual = annual.sort_values(report_col)
    nm_values = annual["销售净利率"].apply(_parse_pct).tolist()
    return nm_values[-years:] if len(nm_values) > years else nm_values


def extract_latest_net_profit(df: pd.DataFrame) -> float:
    """提取最新年报净利润（亿元）"""
    if "净利润" not in df.columns:
        return 0.0

    # 取最新年报（-12-31 结尾的最后一条）
    report_col = "报告期"
    annual = df[df[report_col].astype(str).str.endswith("-12-31")]
    if len(annual) == 0:
        annual = df

    latest = annual.sort_values(report_col).iloc[-1]
    val = latest["净利润"]
    if isinstance(val, str):
        if "万亿" in val:
            return float(val.replace("万亿", "").replace(",", "")) * 10000
        if "亿" in val:
            return float(val.replace("亿", "").replace(",", ""))
        if "万" in val:
            return float(val.replace("万", "").replace(",", "")) / 10000
        return float(val.replace(",", "")) / 1e8
    # 已经是数字（元）
    return float(val) / 1e8


def extract_latest_revenue(df: pd.DataFrame) -> float:
    """提取最新年报营业总收入（亿元）"""
    if "营业总收入" not in df.columns:
        return 0.0

    report_col = "报告期"
    annual = df[df[report_col].astype(str).str.endswith("-12-31")]
    if len(annual) == 0:
        annual = df

    latest = annual.sort_values(report_col).iloc[-1]
    val = latest["营业总收入"]
    if isinstance(val, str):
        if "万亿" in val:
            return float(val.replace("万亿", "").replace(",", "")) * 10000
        if "亿" in val:
            return float(val.replace("亿", "").replace(",", ""))
        if "万" in val:
            return float(val.replace("万", "").replace(",", "")) / 10000
        return float(val.replace(",", "")) / 1e8
    return float(val) / 1e8


def get_buffett_inputs(symbol: str, current_price: float = 0, industry: str = "") -> dict:
    """
    一站式获取巴菲特过滤器所需的全部真实财务参数
    - 股本: 从新浪日线 outstanding_share 取
    - FCF: 从同花顺现金流量表计算 (经营现金流 - 购建固定资产)
    - 增长率: 从近5年净利润增速中位数计算
    """
    from .symbols import SYMBOL_SECTOR, FALLBACK_SECTOR
    from data.ingestion.fetcher import get_stock_daily

    df = get_financial_summary(symbol)
    if len(df) == 0:
        return {}
    if current_price is None or current_price <= 0:
        return {}

    roe_history = extract_roe_history(df)
    gm_history = extract_gross_margin_history(df)
    nm_history = extract_net_margin_history(df)
    debt_ratio = extract_debt_equity_ratio(df)
    net_profit = extract_latest_net_profit(df)

    # 真实股本 — 从新浪日线 outstanding_share 列取
    shares = 0
    try:
        price_df = get_stock_daily(symbol)
        if price_df is not None and "outstanding_share" in price_df.columns:
            shares = float(price_df["outstanding_share"].iloc[-1]) / 1e8  # 转为亿股
    except Exception:
        pass
    if shares <= 0:
        return {}

    # 真实 FCF — 从同花顺现金流量表计算
    fcf = _estimate_fcf(symbol, net_profit)
    if fcf is None or fcf <= 0:
        return {}

    # 增长预期 — 从近5年净利润增速中位数计算
    growth = _estimate_growth(df)
    if growth is None:
        return {}

    # 板块类型
    sector = SYMBOL_SECTOR.get(symbol, FALLBACK_SECTOR)

    return {
        "fcf": fcf,
        "growth_rate": growth,
        "shares_outstanding": shares,
        "current_price": current_price,
        "roe_history": roe_history,
        "gross_margin_history": gm_history,
        "net_margin_history": nm_history,
        "debt_equity": debt_ratio,
        "sector": sector,
        "industry": industry,
    }


# ---- FCF 估算 ----
def _estimate_fcf(symbol: str, net_profit_fallback: float = 0) -> float | None:
    """
    从同花顺现金流量表计算真实 FCF
    FCF = 经营活动现金流净额 - 购建固定资产支付的现金
    失败时返回 None，由上层显式跳过该标的。
    """
    try:
        import akshare as ak
        df = ak.stock_financial_cash_ths(symbol=symbol, indicator="按报告期")
        if df is None or len(df) == 0:
            raise ValueError("无现金流数据")

        # 只取最新年报
        report_col = "报告期"
        if report_col in df.columns:
            annual = df[df[report_col].astype(str).str.endswith("-12-31")]
        else:
            annual = df.copy()
        if len(annual) == 0:
            raise ValueError("无年报现金流")

        if report_col in annual.columns:
            latest = annual.sort_values(report_col).iloc[-1]
        else:
            latest = annual.iloc[-1]

        # 经营活动现金流净额
        ocf_str = str(latest.get("经营活动产生的现金流量净额", "0"))
        ocf = _parse_financial_number(ocf_str)

        # 购建固定资产支付的现金
        capex_cols = [
            "购建固定资产、无形资产和其他长期资产支付的现金",
            "购建固定资产、无形资产和其他长期资产收回的现金净额",  # fallback
        ]
        capex = 0
        for col in capex_cols:
            if col in latest:
                val = str(latest[col])
                if val and val != "nan" and val != "False":
                    capex = _parse_financial_number(val)
                    break

        fcf = ocf - capex
        if fcf > 0:
            return fcf
    except Exception:
        pass

    return None


def _estimate_growth(df: pd.DataFrame) -> float | None:
    """
    从近5年净利润同比增长率中位数估算增长率
    保守下限/上限从 config 读取；缺增长样本时返回 None。
    """
    if "净利润同比增长率" not in df.columns:
        return None

    report_col = "报告期"
    if report_col in df.columns:
        annual = df[df[report_col].astype(str).str.endswith("-12-31")]
    else:
        annual = df.copy()
    if len(annual) < 3:
        return None

    growth_rates = annual["净利润同比增长率"].apply(_parse_pct).tail(5).tolist()
    growth_rates = [g for g in growth_rates if abs(g) < 1.0]  # 过滤异常值 (>100%)
    if not growth_rates:
        return None

    median_growth = np.median(growth_rates)
    return max(_GROWTH_MIN, min(_GROWTH_MAX, median_growth))


def _parse_financial_number(val: str) -> float:
    """解析金融数字: '4.35亿' → 4.35, '1.03万亿' → 10300"""
    val = str(val).replace(",", "").strip()
    if not val or val in ("nan", "False", "None", ""):
        return 0.0
    try:
        if "万亿" in val:
            return float(val.replace("万亿", "")) * 10000
        if "亿" in val:
            return float(val.replace("亿", ""))
        if "万" in val:
            return float(val.replace("万", "")) / 10000
        return float(val) / 1e8
    except ValueError:
        return 0.0
