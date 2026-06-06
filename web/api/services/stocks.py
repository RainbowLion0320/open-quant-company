"""Stock list and stock detail payload builders."""

from __future__ import annotations

import json

from web.api.errors import DataNotFoundError
from web.api.schemas.market import KLineItem
from web.api.schemas.portfolio import FinancialData, StockDetail, StockResponse
from web.api.schemas.strategy import StrategySignal


def build_stock_list(limit: int, q: str = "") -> tuple[list[dict], int]:
    from data.storage.datahub import get_datahub
    from data.strategy.catalog import get_enabled_strategies
    from data.storage.results_db import load_buffett_results, load_strategy_signals
    from data.market.symbols import FALLBACK_SECTOR, SYMBOL_INDUSTRY, SYMBOL_NAME, SYMBOL_SECTOR

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
            score = safe_float(sig.get("score"))
            item = signal_summary.setdefault(
                symbol,
                {"signal_count": 0, "buy_signals": 0, "signal_score": None, "signal": "hold", "top_strategy": ""},
            )
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
        candidates.append(
            {
                "symbol": symbol,
                "name": name,
                "industry": industry,
                "sector": SYMBOL_SECTOR.get(symbol, FALLBACK_SECTOR),
                "buffett_score": safe_float(buffett.get("score")),
                "roe": safe_float(buffett.get("avg_roe_5y")),
                "gross_margin": safe_float(buffett.get("avg_gross_margin_5y")),
                "buffett_price": safe_float(buffett.get("current_price")),
                "buffett_updated_at": str(buffett.get("updated_at") or ""),
                "signal_score": signal.get("signal_score"),
                "signal": signal.get("signal", "hold"),
                "buy_signals": int(signal.get("buy_signals", 0)),
                "signal_count": int(signal.get("signal_count", 0)),
                "top_strategy": signal.get("top_strategy", ""),
            }
        )

    total = len(candidates)
    candidates.sort(key=stock_list_rank, reverse=True)
    rows: list[dict] = []
    visible = candidates[:limit]
    valuations = latest_valuations(hub, [str(base["symbol"]) for base in visible])
    for base in visible:
        valuation = valuations.get(base["symbol"], {})
        base["price"] = first_number(valuation.get("price"), base.pop("buffett_price", None))
        base["change_pct"] = valuation.get("change_pct")
        base["pe_ttm"] = valuation.get("pe_ttm")
        base["pb"] = valuation.get("pb")
        base["total_mv"] = valuation.get("total_mv")
        base["updated_at"] = safe_text(valuation.get("trade_date") or base.pop("buffett_updated_at", ""))
        rows.append(base)

    rows.sort(key=stock_list_rank, reverse=True)
    return rows, total


def build_stock_detail(code: str) -> StockResponse:
    from data.market.financials import (
        extract_debt_equity_ratio,
        extract_gross_margin_history,
        extract_latest_net_profit,
        extract_latest_revenue,
        extract_net_margin_history,
        extract_roe_history,
        get_financial_summary,
    )
    from data.market.price_service import get_stock_prices
    from data.market.price_types import PriceUseCase
    from data.strategy.catalog import get_enabled_strategies
    from data.storage.results_db import load_buffett_results, load_strategy_signals
    from data.market.symbols import FALLBACK_SECTOR, SYMBOL_INDUSTRY, SYMBOL_NAME, SYMBOL_SECTOR

    code = resolve_stock_symbol(code)
    name = SYMBOL_NAME.get(code)
    if not name:
        raise DataNotFoundError("stock", code)

    industry = SYMBOL_INDUSTRY.get(code, "待分类")
    sector = SYMBOL_SECTOR.get(code, FALLBACK_SECTOR)
    basic = StockDetail(symbol=code, name=name, industry=industry, sector=sector)

    financials = []
    try:
        df = get_financial_summary(code)
        if df is not None and len(df) > 0:
            extract_roe_history(df)
            extract_gross_margin_history(df)
            extract_net_margin_history(df)
            de = extract_debt_equity_ratio(df)
            report_col = "报告期"
            annuals = df[df[report_col].astype(str).str.endswith("-12-31")].copy()
            if len(annuals) == 0:
                annuals = df.copy()
            annuals = annuals.sort_values(report_col).tail(6)
            for _, row in annuals.iterrows():
                financials.append(
                    FinancialData(
                        period=str(row.get(report_col, ""))[:10],
                        roe=safe_parse_pct(row.get("净资产收益率")),
                        gross_margin=safe_parse_pct(row.get("销售毛利率")),
                        net_margin=safe_parse_pct(row.get("销售净利率")),
                        debt_equity=de,
                        net_profit=extract_value_float(row.get("净利润")) or extract_latest_net_profit(df),
                        revenue=extract_value_float(row.get("营业总收入")) or extract_latest_revenue(df),
                        profit_growth=None,
                    )
                )
    except Exception:
        pass

    buffett_result = None
    try:
        for row in load_buffett_results(sort="score", order="desc"):
            if row.get("symbol") == code:
                buffett_result = row
                break
    except Exception:
        pass

    signals = []
    for strat in get_enabled_strategies():
        strategy_name = strat["name"]
        try:
            sigs = load_strategy_signals(strategy_name, sort="score", order="desc")
        except Exception:
            sigs = []
        for sg in sigs:
            if sg.get("symbol") != code:
                continue
            detail_val = sg.get("detail")
            if isinstance(detail_val, str) and detail_val.startswith("{"):
                try:
                    detail_val = json.loads(detail_val)
                except Exception:
                    pass
            signals.append(
                StrategySignal(
                    strategy=strategy_name,
                    symbol=sg["symbol"],
                    name=sg.get("name", name),
                    industry=sg.get("industry", industry),
                    score=sg.get("score", 0),
                    signal=sg.get("signal", "hold"),
                    detail=detail_val,
                    computed_at=sg.get("computed_at", ""),
                )
            )
            break

    kline = []
    try:
        kdf = get_stock_prices(code, use_case=PriceUseCase.DISPLAY)
        if kdf is not None and len(kdf) > 0:
            recent = kdf.sort_values("date").tail(120)
            for _, row in recent.iterrows():
                kline.append(
                    KLineItem(
                        date=str(row["date"])[:10],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"]),
                    )
                )
    except Exception:
        pass

    return StockResponse(basic=basic, financials=financials, buffett_result=buffett_result, signals=signals, kline=kline, dcf=None)


def stock_list_rank(row: dict) -> tuple:
    return (
        0 if is_st_stock(row.get("name")) else 1,
        int(row.get("buy_signals") or 0),
        rank_number(row.get("signal_score")),
        rank_number(row.get("buffett_score")),
        rank_number(row.get("total_mv")),
    )


def is_st_stock(name) -> bool:
    return "ST" in str(name or "").upper()


def latest_valuations(hub, symbols: list[str]) -> dict[str, dict]:
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
            price_val = safe_float(price)
            previous_val = safe_float(previous_price)
            change_pct = None
            if price_val is not None and previous_val not in (None, 0):
                change_pct = price_val / previous_val - 1
            total_mv_val = safe_float(total_mv)
            latest[symbol] = {
                "price": price_val,
                "change_pct": change_pct,
                "pe_ttm": safe_float(pe_ttm),
                "pb": safe_float(pb),
                "total_mv": total_mv_val / 10000 if total_mv_val is not None else None,
                "trade_date": safe_text(trade_date),
            }
        return latest
    except Exception:
        return {symbol: latest_valuation(hub, symbol) for symbol in symbol_set}


def latest_valuation(hub, symbol: str) -> dict:
    import pandas as pd

    df = hub.read_parquet(hub.stock_valuation_path(symbol), default=pd.DataFrame())
    if df is None or df.empty:
        return {}
    data = df.copy()
    if "trade_date" in data.columns:
        data = data.sort_values("trade_date")
    latest = data.iloc[-1]
    prev = data.iloc[-2] if len(data) > 1 else latest
    price = safe_float(latest.get("close"))
    prev_price = safe_float(prev.get("close"))
    change_pct = None
    if price is not None and prev_price and prev_price != 0:
        change_pct = price / prev_price - 1
    total_mv = safe_float(latest.get("total_mv"))
    return {
        "price": price,
        "change_pct": change_pct,
        "pe_ttm": safe_float(latest.get("pe_ttm")),
        "pb": safe_float(latest.get("pb")),
        "total_mv": total_mv / 10000 if total_mv is not None else None,
        "trade_date": safe_text(latest.get("trade_date")),
    }


def resolve_stock_symbol(identifier: str) -> str:
    from data.market.symbols import SYMBOL_NAME

    raw = str(identifier or "").strip()
    if raw in SYMBOL_NAME:
        return raw
    needle = raw.lower()
    matches = [symbol for symbol, name in SYMBOL_NAME.items() if needle and (needle in symbol.lower() or needle in str(name).lower())]
    if not matches:
        return raw
    matches.sort(key=lambda symbol: (0 if str(SYMBOL_NAME.get(symbol, "")).lower() == needle else 1, symbol))
    return matches[0]


def safe_float(val):
    if val is None:
        return None
    try:
        if val != val:
            return None
        return float(val)
    except Exception:
        return None


def safe_text(val) -> str:
    if val is None:
        return ""
    try:
        if val != val:
            return ""
    except Exception:
        pass
    text = str(val)
    return "" if text.lower() == "nan" else text


def first_number(*values):
    for value in values:
        number = safe_float(value)
        if number is not None:
            return number
    return None


def rank_number(value):
    number = safe_float(value)
    return number if number is not None else -1e18


def safe_parse_pct(val):
    import pandas as pd

    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        val = val.replace("%", "").replace(",", "")
        try:
            return float(val)
        except ValueError:
            return None
    return None


def extract_value_float(val):
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
