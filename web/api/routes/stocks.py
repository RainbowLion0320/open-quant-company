"""个股深挖路由 — 全景视图 + DCF 估值"""

import json
from fastapi import APIRouter, Query
from web.api.models import DCFParams, DCFResult, StockResponse, StockDetail, StockListResponse, FinancialData, StrategySignal, KLineItem
from web.api.errors import DataNotFoundError, InvalidParameterError

router = APIRouter(prefix="/api/stocks", tags=["Stocks"])


# ── 个股全景 ──────────────────────────────────────────────

@router.get("", response_model=StockListResponse)
async def list_stocks(
    limit: int = Query(default=300, ge=1, le=1000, description="返回股票数量上限"),
    q: str = Query(default="", description="按代码/名称/行业过滤"),
):
    """股票池默认列表: 基础资料 + 估值 + 质量分 + 策略信号摘要."""
    rows, total = _build_stock_list(limit=limit, q=q)
    updated = max((_safe_text(row.get("updated_at")) for row in rows), default="")
    return StockListResponse(stocks=rows, total=total, limit=limit, updated_at=updated)


@router.get("/{code}", response_model=StockResponse)
async def get_stock_detail(code: str):
    """个股全景视图: 基本信息 + 财务 + 巴菲特结果 + 策略信号 + K线"""
    from data.symbols import SYMBOL_NAME, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR
    from data.financials import get_financial_summary, extract_roe_history, extract_gross_margin_history, extract_net_margin_history, extract_debt_equity_ratio, extract_latest_net_profit, extract_latest_revenue
    from data.results_db import load_buffett_results, load_strategy_signals
    from data.fetcher import get_stock_daily

    code = _resolve_stock_symbol(code)

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

def _build_stock_list(limit: int, q: str = "") -> tuple[list[dict], int]:
    from data.datahub import get_datahub
    from data.registry import get_enabled_strategies
    from data.results_db import load_buffett_results, load_strategy_signals
    from data.symbols import SYMBOL_NAME, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR

    hub = get_datahub()
    query = str(q or "").strip().lower()

    buffett_rows = load_buffett_results(sort="score", order="desc")
    buffett_by_symbol = {str(row.get("symbol")): row for row in buffett_rows if row.get("symbol")}

    signal_summary: dict[str, dict] = {}
    for strat in get_enabled_strategies():
        strategy_name = strat["name"]
        try:
            sigs = load_strategy_signals(strategy_name, sort="score", order="desc")
        except Exception:
            sigs = []
        for sig in sigs:
            symbol = str(sig.get("symbol") or "")
            if not symbol:
                continue
            score = _safe_float(sig.get("score"))
            item = signal_summary.setdefault(symbol, {
                "signal_count": 0,
                "buy_signals": 0,
                "signal_score": None,
                "signal": "hold",
                "top_strategy": "",
            })
            item["signal_count"] += 1
            if sig.get("signal") == "buy":
                item["buy_signals"] += 1
                item["signal"] = "buy"
            if score is not None and (item["signal_score"] is None or score > item["signal_score"]):
                item["signal_score"] = score
                item["top_strategy"] = strategy_name

    symbols = sorted(set(SYMBOL_NAME) | set(buffett_by_symbol) | set(signal_summary))
    candidates: list[dict] = []
    for symbol in symbols:
        name = SYMBOL_NAME.get(symbol) or str(buffett_by_symbol.get(symbol, {}).get("name") or symbol)
        industry = SYMBOL_INDUSTRY.get(symbol) or str(buffett_by_symbol.get(symbol, {}).get("industry") or "")
        if query and query not in symbol.lower() and query not in name.lower() and query not in industry.lower():
            continue

        buffett = buffett_by_symbol.get(symbol, {})
        signal = signal_summary.get(symbol, {})
        candidates.append({
            "symbol": symbol,
            "name": name,
            "industry": industry,
            "sector": SYMBOL_SECTOR.get(symbol, FALLBACK_SECTOR),
            "buffett_score": _safe_float(buffett.get("score")),
            "roe": _safe_float(buffett.get("avg_roe_5y")),
            "gross_margin": _safe_float(buffett.get("avg_gross_margin_5y")),
            "buffett_price": _safe_float(buffett.get("current_price")),
            "buffett_updated_at": str(buffett.get("updated_at") or ""),
            "signal_score": signal.get("signal_score"),
            "signal": signal.get("signal", "hold"),
            "buy_signals": int(signal.get("buy_signals", 0)),
            "signal_count": int(signal.get("signal_count", 0)),
            "top_strategy": signal.get("top_strategy", ""),
        })

    total = len(candidates)
    candidates.sort(key=_stock_list_rank, reverse=True)
    rows: list[dict] = []
    visible = candidates[:limit]
    valuations = _latest_valuations(hub, [str(base["symbol"]) for base in visible])
    for base in visible:
        valuation = valuations.get(base["symbol"], {})
        base["price"] = _first_number(valuation.get("price"), base.pop("buffett_price", None))
        base["change_pct"] = valuation.get("change_pct")
        base["pe_ttm"] = valuation.get("pe_ttm")
        base["pb"] = valuation.get("pb")
        base["total_mv"] = valuation.get("total_mv")
        base["updated_at"] = _safe_text(valuation.get("trade_date") or base.pop("buffett_updated_at", ""))
        rows.append(base)

    rows.sort(key=_stock_list_rank, reverse=True)
    return rows, total


def _stock_list_rank(row: dict) -> tuple:
    return (
        0 if _is_st_stock(row.get("name")) else 1,
        int(row.get("buy_signals") or 0),
        _rank_number(row.get("signal_score")),
        _rank_number(row.get("buffett_score")),
        _rank_number(row.get("total_mv")),
    )


def _is_st_stock(name) -> bool:
    text = str(name or "").upper()
    return "ST" in text


def _latest_valuations(hub, symbols: list[str]) -> dict[str, dict]:
    symbol_set = {str(symbol) for symbol in symbols if symbol}
    if not symbol_set:
        return {}

    try:
        import duckdb

        valuation_glob = str(hub.store_path("stock") / "valuation" / "*.parquet")
        con = duckdb.connect(database=":memory:")
        try:
            rows = con.execute(
                """
                WITH ranked AS (
                  SELECT
                    regexp_extract(filename, '([^/]+)\\.parquet$', 1) AS symbol,
                    trade_date,
                    close,
                    pe_ttm,
                    pb,
                    total_mv,
                    row_number() OVER (PARTITION BY filename ORDER BY trade_date DESC) AS rn
                  FROM read_parquet(?, filename=true)
                )
                SELECT
                  latest.symbol,
                  latest.trade_date,
                  latest.close,
                  previous.close AS previous_close,
                  latest.pe_ttm,
                  latest.pb,
                  latest.total_mv
                FROM ranked latest
                LEFT JOIN ranked previous ON latest.symbol = previous.symbol AND previous.rn = 2
                WHERE latest.rn = 1
                """,
                [valuation_glob],
            ).fetchall()
        finally:
            con.close()

        latest: dict[str, dict] = {}
        for symbol, trade_date, price, previous_price, pe_ttm, pb, total_mv in rows:
            symbol = str(symbol)
            if symbol not in symbol_set:
                continue
            price_val = _safe_float(price)
            previous_val = _safe_float(previous_price)
            change_pct = None
            if price_val is not None and previous_val not in (None, 0):
                change_pct = price_val / previous_val - 1
            total_mv_val = _safe_float(total_mv)
            latest[symbol] = {
                "price": price_val,
                "change_pct": change_pct,
                "pe_ttm": _safe_float(pe_ttm),
                "pb": _safe_float(pb),
                "total_mv": total_mv_val / 10000 if total_mv_val is not None else None,
                "trade_date": _safe_text(trade_date),
            }
        return latest
    except Exception:
        return {symbol: _latest_valuation(hub, symbol) for symbol in symbol_set}


def _latest_valuation(hub, symbol: str) -> dict:
    import pandas as pd

    pq = hub.stock_valuation_path(symbol)
    df = hub.read_parquet(pq, default=pd.DataFrame())
    if df is None or df.empty:
        return {}
    data = df.copy()
    if "trade_date" in data.columns:
        data = data.sort_values("trade_date")
    latest = data.iloc[-1]
    prev = data.iloc[-2] if len(data) > 1 else latest
    price = _safe_float(latest.get("close"))
    prev_price = _safe_float(prev.get("close"))
    change_pct = None
    if price is not None and prev_price and prev_price != 0:
        change_pct = price / prev_price - 1
    total_mv = _safe_float(latest.get("total_mv"))
    return {
        "price": price,
        "change_pct": change_pct,
        "pe_ttm": _safe_float(latest.get("pe_ttm")),
        "pb": _safe_float(latest.get("pb")),
        "total_mv": total_mv / 10000 if total_mv is not None else None,
        "trade_date": _safe_text(latest.get("trade_date")),
    }


def _resolve_stock_symbol(identifier: str) -> str:
    from data.symbols import SYMBOL_NAME

    raw = str(identifier or "").strip()
    if raw in SYMBOL_NAME:
        return raw
    needle = raw.lower()
    matches = [
        symbol for symbol, name in SYMBOL_NAME.items()
        if needle and (needle in symbol.lower() or needle in str(name).lower())
    ]
    if not matches:
        return raw
    matches.sort(key=lambda symbol: (
        0 if str(SYMBOL_NAME.get(symbol, "")).lower() == needle else 1,
        symbol,
    ))
    return matches[0]


def _safe_float(val):
    if val is None:
        return None
    try:
        if val != val:
            return None
        return float(val)
    except Exception:
        return None


def _safe_text(val) -> str:
    if val is None:
        return ""
    try:
        if val != val:
            return ""
    except Exception:
        pass
    text = str(val)
    return "" if text.lower() == "nan" else text


def _first_number(*values):
    for value in values:
        number = _safe_float(value)
        if number is not None:
            return number
    return None


def _rank_number(value):
    number = _safe_float(value)
    return number if number is not None else -1e18


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
