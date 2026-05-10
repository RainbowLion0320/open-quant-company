"""
财务数据桥接层 — 从 AKShare 提取 ROE/毛利率/负债率，驱动巴菲特过滤器
数据源：同花顺 (stock_financial_abstract_ths)
"""
from typing import Tuple, List, Optional
import pandas as pd
import numpy as np

from .fetcher import get_financial_indicator, retry_with_backoff

# ---- 内存缓存 ----
_financial_cache: dict = {}


def _parse_pct(val) -> float:
    """解析百分比字符串 '54.27%' → 0.5427"""
    if isinstance(val, (int, float)):
        return float(val) / 100 if abs(float(val)) > 1 else float(val)
    if isinstance(val, str):
        val = val.replace("%", "").replace(",", "")
        try:
            f = float(val)
            return f / 100 if abs(f) > 1 else f
        except ValueError:
            return 0.0
    return 0.0


@retry_with_backoff(max_retries=2, base_delay=2.0)
def get_financial_summary(symbol: str, force_refresh: bool = False) -> pd.DataFrame:
    """
    获取个股财务摘要（同花顺源）
    返回包含 ROE、毛利率、资产负债率等核心指标的 DataFrame
    列: 报告期, 净利润, 营业总收入, 净资产收益率, 销售毛利率, 资产负债率, ...
    """
    cache_key = f"financial_summary_{symbol}"
    if not force_refresh and cache_key in _financial_cache:
        return _financial_cache[cache_key]

    # 尝试同花顺源（更稳定）
    try:
        import akshare as ak
        df = ak.stock_financial_abstract_ths(symbol=symbol, indicator="按报告期")
    except Exception:
        # 回退到通用源
        df = get_financial_indicator(symbol, force_refresh=force_refresh)

    if len(df) == 0:
        return df

    _financial_cache[cache_key] = df
    return df


def extract_roe_history(df: pd.DataFrame, years: int = 5) -> List[float]:
    """
    从财务摘要 DataFrame 提取近N年 ROE 序列（仅取年报）
    返回: [ROE_year1, ROE_year2, ...] 从旧到新排列
    """
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


def extract_gross_margin_history(df: pd.DataFrame, years: int = 5) -> List[float]:
    """
    从财务摘要提取近N年毛利率序列（仅取年报）
    """
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
    # 优先：产权比率 直接就是 D/E
    if "产权比率" in df.columns:
        # 取最新年报的产权比率
        report_col = "报告期"
        annual = df[df[report_col].astype(str).str.endswith("-12-31")]
        if len(annual) == 0:
            annual = df
        latest = annual.sort_values(report_col).iloc[-1]
        val = latest["产权比率"]
        try:
            f = float(val)
            return f if f > 0 else 0.0
        except (ValueError, TypeError):
            return 0.0

    # 回退：资产负债率 → D/E = debt_ratio / (1 - debt_ratio)
    if "资产负债率" not in df.columns:
        return 0.0

    latest = df.sort_values("报告期").iloc[-1]
    debt_ratio = _parse_pct(latest["资产负债率"])
    if debt_ratio >= 1.0:
        return 99.0  # 极端情况
    return debt_ratio / (1 - debt_ratio) if debt_ratio < 1 else 99.0


def extract_net_margin_history(df: pd.DataFrame, years: int = 5) -> List[float]:
    """
    从财务摘要提取近N年销售净利率序列（仅取年报）
    用于金融板块替代毛利率
    """
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
        return float(val.replace(",", ""))
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
        return float(val.replace(",", ""))
    return float(val) / 1e8


def get_buffett_inputs(symbol: str, current_price: float = 0, industry: str = "") -> dict:
    """
    一站式获取巴菲特过滤器所需的全部真实财务参数
    - 股本: 从新浪日线 outstanding_share 取
    - FCF: 从同花顺现金流量表计算 (经营现金流 - 购建固定资产)
    - 增长率: 从近5年净利润增速中位数计算
    """
    from .symbols import SYMBOL_SECTOR, FALLBACK_SECTOR
    from .fetcher import get_stock_daily

    df = get_financial_summary(symbol)
    if len(df) == 0:
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

    # 真实 FCF — 从同花顺现金流量表计算
    fcf = _estimate_fcf(symbol, net_profit)

    # 增长预期 — 从近5年净利润增速中位数计算
    growth = _estimate_growth(df)

    # 板块类型
    sector = SYMBOL_SECTOR.get(symbol, FALLBACK_SECTOR)

    return {
        "fcf": fcf,
        "growth_rate": growth,
        "shares_outstanding": max(shares, 0.1),  # 至少 0.1 亿股防止除零
        "current_price": current_price,
        "roe_history": roe_history,
        "gross_margin_history": gm_history,
        "net_margin_history": nm_history,
        "debt_equity": debt_ratio,
        "sector": sector,
        "industry": industry,
    }


# ---- FCF 估算 ----
def _estimate_fcf(symbol: str, net_profit_fallback: float = 0) -> float:
    """
    从同花顺现金流量表计算真实 FCF
    FCF = 经营活动现金流净额 - 购建固定资产支付的现金
    失败时回退到净利润 × 0.7
    """
    try:
        import akshare as ak
        df = ak.stock_financial_cash_ths(symbol=symbol, indicator="按报告期")
        if df is None or len(df) == 0:
            raise ValueError("无现金流数据")

        # 只取最新年报
        annual = df[df["报告期"].astype(str).str.endswith("-12-31")]
        if len(annual) == 0:
            raise ValueError("无年报现金流")

        latest = annual.sort_values("报告期").iloc[-1]

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

    # 回退
    return net_profit_fallback * 0.7 if net_profit_fallback > 0 else 0


def _estimate_growth(df: pd.DataFrame) -> float:
    """
    从近5年净利润同比增长率中位数估算增长率
    保守下限 0.03, 上限 0.12
    """
    if "净利润同比增长率" not in df.columns:
        return 0.05

    annual = df[df["报告期"].astype(str).str.endswith("-12-31")]
    if len(annual) < 3:
        return 0.05

    growth_rates = annual["净利润同比增长率"].apply(_parse_pct).tail(5).tolist()
    growth_rates = [g for g in growth_rates if abs(g) < 1.0]  # 过滤异常值 (>100%)
    if not growth_rates:
        return 0.05

    median_growth = np.median(growth_rates)
    return max(0.03, min(0.12, median_growth))


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
        return float(val)
    except ValueError:
        return 0.0
