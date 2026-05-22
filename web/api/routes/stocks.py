"""个股深挖路由 — 全景视图 + DCF 估值"""

import json
from fastapi import APIRouter, Query
from web.api.models import DCFParams, DCFResult, StockResponse, StockDetail, FinancialData, StrategySignal, KLineItem
from web.api.errors import DataNotFoundError, InvalidParameterError

router = APIRouter(prefix="/api/stocks", tags=["Stocks"])


# ── 个股全景 ──────────────────────────────────────────────

@router.get("/{code}", response_model=StockResponse)
async def get_stock_detail(code: str):
    """个股全景视图: 基本信息 + 财务 + 巴菲特结果 + 策略信号 + K线"""
    from data.symbols import SYMBOL_NAME, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR
    from data.financials import get_financial_summary, extract_roe_history, extract_gross_margin_history, extract_net_margin_history, extract_debt_equity_ratio, extract_latest_net_profit, extract_latest_revenue
    from data.results_db import load_buffett_results, load_strategy_signals
    from data.fetcher import get_stock_daily

    # 验码
    name = SYMBOL_NAME.get(code)
    if not name:
        raise DataNotFoundError("stock", code)

    industry = SYMBOL_INDUSTRY.get(code, "待分类")
    sector = SYMBOL_SECTOR.get(code, FALLBACK_SECTOR)

    basic = StockDetail(symbol=code, name=name, industry=industry, sector=sector)

    # ── 财务数据 ──
    financials = []
    try:
        df = get_financial_summary(code)
        if df is not None and len(df) > 0:
            roe_hist = extract_roe_history(df)
            gm_hist = extract_gross_margin_history(df)
            nm_hist = extract_net_margin_history(df)
            de = extract_debt_equity_ratio(df)
            np_val = extract_latest_net_profit(df)
            rev = extract_latest_revenue(df)

            # 构建财务时间序列 (只取最近5个年报期)
            report_col = "报告期"
            annuals = df[df[report_col].astype(str).str.endswith("-12-31")].copy()
            if len(annuals) == 0:
                annuals = df.copy()
            annuals = annuals.sort_values(report_col).tail(6)

            for _, row in annuals.iterrows():
                period = str(row.get(report_col, ""))[:10]
                financials.append(FinancialData(
                    period=period,
                    roe=_safe_parse_pct(row.get("净资产收益率")),
                    gross_margin=_safe_parse_pct(row.get("销售毛利率")),
                    net_margin=_safe_parse_pct(row.get("销售净利率")),
                    debt_equity=de,
                    net_profit=_extract_value_float(row.get("净利润")),
                    revenue=_extract_value_float(row.get("营业总收入")),
                    profit_growth=None,  # 需要多期对比才能算
                ))
    except Exception:
        pass  # 财务获取失败不阻断

    # ── 巴菲特结果 ──
    buffett_result = None
    try:
        buffett_rows = load_buffett_results(sort="score", order="desc")
        for r in buffett_rows:
            if r.get("symbol") == code:
                buffett_result = r
                break
    except Exception:
        pass

    # ── 策略信号 ──
    signals = []
    from data.registry import get_enabled_strategies
    for strat in get_enabled_strategies():
        strategy_name = strat["name"]
        try:
            sigs = load_strategy_signals(strategy_name, sort="score", order="desc")
            for sg in sigs:
                if sg.get("symbol") == code:
                    detail_val = sg.get("detail")
                    if isinstance(detail_val, str) and detail_val.startswith("{"):
                        try:
                            detail_val = json.loads(detail_val)
                        except Exception:
                            pass
                    signals.append(StrategySignal(
                        strategy=strategy_name,
                        symbol=sg["symbol"],
                        name=sg.get("name", name),
                        industry=sg.get("industry", industry),
                        score=sg.get("score", 0),
                        signal=sg.get("signal", "hold"),
                        detail=detail_val,
                        computed_at=sg.get("computed_at", ""),
                    ))
                    break
        except Exception:
            pass

    # ── K线 ──
    kline = []
    try:
        kdf = get_stock_daily(code)
        if kdf is not None and len(kdf) > 0:
            recent = kdf.sort_values("date").tail(120)
            for _, row in recent.iterrows():
                kline.append(KLineItem(
                    date=str(row["date"])[:10],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                ))
    except Exception:
        pass

    return StockResponse(
        basic=basic,
        financials=financials,
        buffett_result=buffett_result,
        signals=signals,
        kline=kline,
        dcf=None,
    )


# ── DCF 估值计算 ──────────────────────────────────────────

@router.post("/dcf", response_model=DCFResult)
async def compute_dcf(
    code: str = Query(..., description="股票代码"),
    params: DCFParams = None,
):
    """DCF 估值计算: 给定 FCF + 增长 + 折现率, 返回内在价值与安全边际"""
    from data.fetcher import get_stock_daily

    if params is None:
        raise InvalidParameterError("params", "missing", "DCFParams body required")

    # 获取当前价格
    current_price = 0.0
    try:
        kdf = get_stock_daily(code)
        if kdf is not None and len(kdf) > 0:
            current_price = float(kdf.sort_values("date").iloc[-1]["close"])
    except Exception:
        pass

    # 获取股本
    shares = params.shares
    if shares <= 0:
        try:
            kdf = get_stock_daily(code)
            if kdf is not None and "outstanding_share" in kdf.columns:
                shares = float(kdf["outstanding_share"].iloc[-1]) / 1e8
        except Exception:
            shares = 1.0  # 回退

    # DCF 两阶段模型
    fcf = params.fcf  # 亿
    g = params.growth_rate  # 高速增长期增长率
    tg = params.terminal_growth  # 永续增长率
    r = params.discount_rate  # 折现率

    if g >= r:
        g = r * 0.9  # 增长率不可超过折现率
    if tg >= r:
        tg = r * 0.5  # 永续增长率必须低于折现率

    # 第一阶段: 5年高速增长
    stage1_pv = 0
    fcf_t = fcf
    for year in range(1, 6):
        fcf_t *= (1 + g)
        stage1_pv += fcf_t / ((1 + r) ** year)

    # 第二阶段: 永续 (Gordon Growth)
    terminal_fcf = fcf_t * (1 + tg)
    terminal_value = terminal_fcf / (r - tg)
    stage2_pv = terminal_value / ((1 + r) ** 5)

    intrinsic_value_per_share = (stage1_pv + stage2_pv) / shares  # 每股内在价值(元)
    safety_margin_pct = ((intrinsic_value_per_share - current_price) / intrinsic_value_per_share) * 100 if intrinsic_value_per_share > 0 else 0

    if safety_margin_pct >= 30:
        verdict = "underpriced"
    elif safety_margin_pct >= 0:
        verdict = "fair"
    elif safety_margin_pct >= -10:
        verdict = "slightly_overpriced"
    else:
        verdict = "overpriced"

    return DCFResult(
        intrinsic_value=round(intrinsic_value_per_share, 2),
        current_price=round(current_price, 2),
        safety_margin=round(safety_margin_pct, 1),
        verdict=verdict,
    )


# ── 辅助 ──────────────────────────────────────────────────

def _safe_parse_pct(val):
    import pandas as pd
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.replace("%", "").replace(",", "")
        try:
            f = float(val)
            return f
        except ValueError:
            return None
    return None


def _extract_value_float(val):
    import pandas as pd
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        if "万亿" in val:
            return float(val.replace("万亿", "").replace(",", "")) * 10000
        if "亿" in val:
            return float(val.replace("亿", "").replace(",", ""))
        if "万" in val:
            return float(val.replace("万", "").replace(",", "")) / 10000
        try:
            return float(val.replace(",", ""))
        except ValueError:
            return None
    return None
