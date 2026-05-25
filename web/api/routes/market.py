"""市场数据路由"""

from fastapi import APIRouter, Query
from datetime import datetime
import pandas as pd

from data.datahub import get_datahub
from web.api.serializers import date_value_series, safe_float, series_card
from web.api.version import get_project_meta

router = APIRouter(prefix="/api/market", tags=["Market"])

HUB = get_datahub()

# Kline range → tail rows mapping
_RANGE_TAIL = {"1D": 2, "1M": 22, "6M": 126, "YTD": 252}

_CORE_INDEX_CARDS = [
    ("sse", "上证综指", "000001.SH", "sh000001", "上证综指 OHLCV"),
    ("csi300", "沪深300", "000300.SH", "sh000300", "沪深300指数 OHLCV"),
    ("chinext", "创业板指", "399006.SZ", "sz399006", "创业板指 OHLCV"),
    ("star50", "科创50", "000688.SH", "sh000688", "科创50指数 OHLCV"),
]
_REGIME_KEYS = ("bull", "sideways", "bear")


def _num(v, default=0.0) -> float:
    return safe_float(v, default)


def _position_capacity(current: object) -> dict[str, int]:
    current_positions = max(0, int(_num(current, 0)))
    configured_max = current_positions

    try:
        from cybernetics.orchestrator import MarketRegime, adaptive_params

        for key in _REGIME_KEYS:
            params = adaptive_params(MarketRegime(key))
            configured_max = max(configured_max, int(_num(params.get("max_positions"), 0)))
    except Exception:
        configured_max = max(configured_max, 8)

    return {"current": current_positions, "max": max(configured_max, 1)}


def _series_card(key: str, label: str, symbol: str, df: pd.DataFrame | None, value_col: str = "close", unit: str = "",
                 data_source: str = "real", source_detail: str = "", series_limit: int = 42) -> dict:
    return series_card(key, label, symbol, df, value_col, unit, data_source, source_detail, series_limit)


def _load_etf(symbol: str) -> pd.DataFrame | None:
    """Load cached ETF data only; the dashboard must not block on network fetches."""
    path = HUB.asset_daily_path("etf", symbol)
    if not path.exists():
        return None
    try:
        df = HUB.read_parquet(path)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    except Exception:
        return None


def _load_bond_yield() -> pd.DataFrame | None:
    path = HUB.store_dir("bond") / "treasury_yields.parquet"
    if not path.exists():
        return None
    try:
        df = HUB.read_parquet(path).reset_index(drop=True)
        if "日期" in df.columns:
            df["date"] = pd.to_datetime(df["日期"], errors="coerce")
        return df
    except Exception:
        return None


def _load_index(symbol: str) -> tuple[pd.DataFrame | None, str, str]:
    try:
        from data.fetcher import get_index_daily
        df = get_index_daily(symbol)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df.dropna(subset=["date"]).sort_values("date"), "real", "AKShare stock_zh_index_daily"
    except Exception as exc:
        return None, "missing", f"{symbol} 指数行情加载失败: {type(exc).__name__}"


def _load_macro(name: str) -> pd.DataFrame | None:
    path = HUB.macro_path(name)
    if not path.exists():
        return None
    try:
        df = HUB.read_parquet(path)
        if "date" not in df.columns:
            # Try date-like columns: "date", "日期", "quarter" (e.g. "2024Q4")
            date_col = next((c for c in df.columns if "date" in str(c).lower() or "日期" in str(c)), None)
            if date_col:
                df = df.rename(columns={date_col: "date"})
            elif "quarter" in df.columns:
                def _quarter_to_date(q: str) -> str:
                    """Convert '2024Q4' → '2024-10-01'"""
                    q = str(q).strip()
                    m = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}
                    for suffix, month in m.items():
                        if suffix in q:
                            return q.replace(suffix, "") + "-" + month + "-01"
                    return q
                df["date"] = df["quarter"].apply(_quarter_to_date)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df.dropna(subset=["date"]).sort_values("date")
    except Exception:
        return None


def _macro_card(key: str, label: str, df: pd.DataFrame | None, candidates: list[str], unit: str = "%") -> dict:
    if df is None or len(df) == 0:
        return {"key": key, "label": label, "value": None, "prev": None, "unit": unit, "date": "", "series": []}
    col = next((c for c in candidates if c in df.columns), None)
    if col is None:
        numeric = [c for c in df.columns if c != "date" and pd.api.types.is_numeric_dtype(df[c])]
        col = numeric[0] if numeric else None
    if col is None:
        return {"key": key, "label": label, "value": None, "prev": None, "unit": unit, "date": "", "series": []}
    clean = df.dropna(subset=[col]).tail(36)
    if len(clean) == 0:
        return {"key": key, "label": label, "value": None, "prev": None, "unit": unit, "date": "", "series": []}
    latest = clean.iloc[-1]
    prev = clean.iloc[-2] if len(clean) > 1 else latest
    return {
        "key": key,
        "label": label,
        "value": round(_num(latest[col]), 4),
        "prev": round(_num(prev[col]), 4),
        "unit": unit,
        "date": str(latest["date"])[:10],
        "series": date_value_series(clean, col, limit=36),
    }


def _multi_asset_cards(bench: pd.DataFrame, series_limit: int = 42) -> list[dict]:
    """Keep the API field for compatibility, but render core index breadth cards."""
    cards = []
    bench_len = len(bench)
    for key, label, display_symbol, fetch_symbol, source_detail in _CORE_INDEX_CARDS:
        if key == "sse":
            df = bench
            data_source = "real"
            detail = source_detail
        else:
            df, data_source, provider_detail = _load_index(fetch_symbol)
            if df is not None and bench_len:
                df = df.tail(bench_len)
            detail = f"{source_detail} · {provider_detail}" if data_source == "real" else provider_detail
        cards.append(_series_card(key, label, display_symbol, df, "close", "",
                                  data_source=data_source, source_detail=detail,
                                  series_limit=series_limit))
    return cards


def _macro_cards() -> list[dict]:
    return [
        _macro_card("gdp", "GDP YoY", _load_macro("gdp"), ["gdp_yoy", "GDP_同比", "今值"]),
        _macro_card("pmi", "制造业 PMI", _load_macro("pmi"), ["pmi_mfg", "PMI010000", "今值"]),
        _macro_card("cpi", "CPI YoY", _load_macro("cpi"), ["nt_yoy", "cpi_yoy", "CPI_全国_同比", "今值"]),
        _macro_card("shibor", "SHIBOR 7D", _load_macro("shibor"), ["1W", "1W-定价"]),
    ]


@router.get("/regime")
async def market_regime():
    """轻量端点: 仅返回顶栏遥测所需数据 (regime + 核心指数 + 新鲜度)。App.vue 每60s轮询。"""
    from cybernetics.orchestrator import QuantOrchestrator
    from data.fetcher import get_index_daily

    orch = QuantOrchestrator()
    snapshot = orch.detect()

    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])
    multi_asset = _multi_asset_cards(bench)
    max_positions = orch.params.get("max_positions", 0)

    return {
        "regime": {
            "value": snapshot.regime.value,
            "score": snapshot.regime_score,
            "ma_trend": snapshot.index_ma_trend,
            "volume_trend": snapshot.volume_trend,
            "breadth": round(snapshot.breadth, 2),
            "breadth_detail": snapshot.breadth_detail,
            "score_components": snapshot.score_components,
        },
        "multi_asset": multi_asset,
        "freshness": {
            "market": str(bench.iloc[-1]["date"])[:10] if len(bench) else "",
        },
        "config": {
            "project": get_project_meta(),
        },
        "position_capacity": _position_capacity(max_positions),
        "updated": datetime.now().strftime("%H:%M"),
    }


@router.get("")
async def market_overview(range: str = Query(default="6M", pattern="^(1D|1M|6M|YTD)$")):
    """市场总览: regime + K线 + 核心指数 + 宏观"""
    from cybernetics.orchestrator import QuantOrchestrator

    orch = QuantOrchestrator()
    snapshot = orch.detect()

    from data.fetcher import get_index_daily
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])

    tail = _RANGE_TAIL.get(range, 126)
    recent = bench.tail(tail)

    kline = []
    for _, row in recent.iterrows():
        kline.append({
            "date": str(row["date"])[:10],
            "close": float(row["close"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": int(row["volume"]),
        })

    regime = {
        "value": snapshot.regime.value,
        "score": snapshot.regime_score,
        "ma_trend": snapshot.index_ma_trend,
        "volume_trend": snapshot.volume_trend,
        "breadth": round(snapshot.breadth, 2),
        "breadth_detail": snapshot.breadth_detail,
        "score_components": snapshot.score_components,
    }
    multi_asset = _multi_asset_cards(recent, series_limit=tail)
    macro = _macro_cards()

    max_positions = orch.params.get("max_positions", 0)

    return {
        "regime": regime,
        "kline": kline,
        "range": range,
        "multi_asset": multi_asset,
        "macro": macro,
        "freshness": {
            "market": str(recent.iloc[-1]["date"])[:10] if len(recent) else "",
            "macro": max([m.get("date", "") for m in macro] or [""]),
        },
        "pool_size": max_positions,
        "position_capacity": _position_capacity(max_positions),
        "config": {
            "project": get_project_meta(),
        },
        "updated": datetime.now().strftime("%H:%M"),
    }
