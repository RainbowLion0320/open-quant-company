"""Market API domain service."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd

from data.datahub import get_datahub
from web.api.serializers import date_value_series, safe_float, series_card
from web.api.version import get_project_meta

HUB = get_datahub()

RANGE_TAIL = {"1D": 2, "1M": 22, "6M": 126, "YTD": 252}
CORE_INDEX_CARDS = [
    ("sse", "上证综指", "000001.SH", "sh000001", "上证综指 OHLCV"),
    ("csi300", "沪深300", "000300.SH", "sh000300", "沪深300指数 OHLCV"),
    ("chinext", "创业板指", "399006.SZ", "sz399006", "创业板指 OHLCV"),
    ("star50", "科创50", "000688.SH", "sh000688", "科创50指数 OHLCV"),
]
REGIME_KEYS = ("bull", "sideways", "bear")


def position_capacity(current: object) -> dict[str, int]:
    current_positions = max(0, int(safe_float(current, 0)))
    configured_max = current_positions

    try:
        from cybernetics.orchestrator import MarketRegime, adaptive_params

        for key in REGIME_KEYS:
            params = adaptive_params(MarketRegime(key))
            configured_max = max(configured_max, int(safe_float(params.get("max_positions"), 0)))
    except Exception:
        configured_max = max(configured_max, 8)

    return {"current": current_positions, "max": max(configured_max, 1)}


def load_index(symbol: str) -> tuple[pd.DataFrame | None, str, str]:
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
            date_col = next((c for c in df.columns if "date" in str(c).lower() or "日期" in str(c)), None)
            if date_col:
                df = df.rename(columns={date_col: "date"})
            elif "quarter" in df.columns:
                df["date"] = df["quarter"].apply(_quarter_to_date)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df.dropna(subset=["date"]).sort_values("date")
    except Exception:
        return None


def _quarter_to_date(q: str) -> str:
    text = str(q).strip()
    months = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}
    for suffix, month in months.items():
        if suffix in text:
            return text.replace(suffix, "") + "-" + month + "-01"
    return text


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
        "value": round(safe_float(latest[col]), 4),
        "prev": round(safe_float(prev[col]), 4),
        "unit": unit,
        "date": str(latest["date"])[:10],
        "series": date_value_series(clean, col, limit=36),
    }


def macro_cards() -> list[dict]:
    return [
        _macro_card("gdp", "GDP YoY", _load_macro("gdp"), ["gdp_yoy", "GDP_同比", "今值"]),
        _macro_card("pmi", "制造业 PMI", _load_macro("pmi"), ["pmi_mfg", "PMI010000", "今值"]),
        _macro_card("cpi", "CPI YoY", _load_macro("cpi"), ["nt_yoy", "cpi_yoy", "CPI_全国_同比", "今值"]),
        _macro_card("shibor", "SHIBOR 7D", _load_macro("shibor"), ["1W", "1W-定价"]),
    ]


def multi_asset_cards(
    bench: pd.DataFrame,
    series_limit: int = 42,
    *,
    load_index_fn: Callable[[str], tuple[pd.DataFrame | None, str, str]] | None = None,
) -> list[dict]:
    """Render core index breadth cards for the market overview."""
    loader = load_index_fn or load_index
    cards = []
    bench_len = len(bench)
    for key, label, display_symbol, fetch_symbol, source_detail in CORE_INDEX_CARDS:
        if key == "sse":
            df = bench
            data_source = "real"
            detail = source_detail
        else:
            df, data_source, provider_detail = loader(fetch_symbol)
            if df is not None and bench_len:
                df = df.tail(bench_len)
            detail = f"{source_detail} · {provider_detail}" if data_source == "real" else provider_detail
        cards.append(series_card(
            key, label, display_symbol, df, "close", "",
            data_source=data_source, source_detail=detail, series_limit=series_limit,
        ))
    return cards


def regime_payload(snapshot) -> dict:
    raw_regime = getattr(snapshot, "raw_regime", snapshot.regime)
    stability = getattr(snapshot, "regime_state", {}) or {}
    value = snapshot.regime.value if hasattr(snapshot.regime, "value") else str(snapshot.regime)
    raw_value = raw_regime.value if hasattr(raw_regime, "value") else str(raw_regime)
    return {
        "value": value,
        "raw_value": raw_value,
        "score": snapshot.regime_score,
        "ma_trend": snapshot.index_ma_trend,
        "volume_trend": snapshot.volume_trend,
        "breadth": round(snapshot.breadth, 2),
        "breadth_detail": snapshot.breadth_detail,
        "score_components": snapshot.score_components,
        "stability": stability,
    }


def kline_series(df: pd.DataFrame) -> list[dict]:
    return [
        {
            "date": str(row["date"])[:10],
            "close": float(row["close"]),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": int(row["volume"]),
        }
        for _, row in df.iterrows()
    ]


def build_market_regime() -> dict:
    from cybernetics.orchestrator import QuantOrchestrator
    from data.fetcher import get_index_daily

    orch = QuantOrchestrator()
    snapshot = orch.detect()
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])
    max_positions = orch.params.get("max_positions", 0)

    return {
        "regime": regime_payload(snapshot),
        "multi_asset": multi_asset_cards(bench),
        "freshness": {"market": str(bench.iloc[-1]["date"])[:10] if len(bench) else ""},
        "config": {"project": get_project_meta()},
        "position_capacity": position_capacity(max_positions),
        "updated": datetime.now().strftime("%H:%M"),
    }


def build_market_overview(range_key: str) -> dict:
    from cybernetics.orchestrator import QuantOrchestrator
    from data.fetcher import get_index_daily

    orch = QuantOrchestrator()
    snapshot = orch.detect()
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])

    tail = RANGE_TAIL.get(range_key, 126)
    recent = bench.tail(tail)
    macro = macro_cards()
    max_positions = orch.params.get("max_positions", 0)

    return {
        "regime": regime_payload(snapshot),
        "kline": kline_series(recent),
        "range": range_key,
        "multi_asset": multi_asset_cards(recent, series_limit=tail),
        "macro": macro,
        "freshness": {
            "market": str(recent.iloc[-1]["date"])[:10] if len(recent) else "",
            "macro": max([m.get("date", "") for m in macro] or [""]),
        },
        "pool_size": max_positions,
        "position_capacity": position_capacity(max_positions),
        "config": {"project": get_project_meta()},
        "updated": datetime.now().strftime("%H:%M"),
    }
