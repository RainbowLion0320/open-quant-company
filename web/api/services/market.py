"""Market API domain service."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd

from data.storage.datahub import get_datahub
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
        from data.ingestion.fetcher import get_index_daily

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
        if name == "money_supply":
            cache_timestamp = pd.Timestamp(path.stat().st_mtime, unit="s")
            df = _restore_money_supply_dates(df, reference_date=cache_timestamp)
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


def _last_complete_month_start(reference_date: pd.Timestamp | None = None) -> pd.Timestamp:
    reference = pd.Timestamp.today().normalize() if reference_date is None else pd.Timestamp(reference_date).normalize()
    return reference.replace(day=1) - pd.DateOffset(months=1)


def _restore_money_supply_dates(
    df: pd.DataFrame,
    reference_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Repair legacy money_supply cache rows whose AKShare month column became NaT."""
    if "date" not in df.columns or len(df) == 0:
        return df

    dates = pd.to_datetime(df["date"], errors="coerce")
    if not dates.isna().all():
        out = df.copy()
        out["date"] = dates
        return out

    out = df.copy()
    latest = _last_complete_month_start(reference_date)
    inferred = pd.date_range(end=latest, periods=len(out), freq="MS")
    out["date"] = list(reversed(inferred))
    return out


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


def _empty_macro_card(key: str, label: str, unit: str = "%") -> dict:
    return {"key": key, "label": label, "value": None, "prev": None, "unit": unit, "date": "", "series": []}


def _macro_series_frame(df: pd.DataFrame | None, candidates: list[str]) -> pd.DataFrame:
    if df is None or len(df) == 0 or "date" not in df.columns:
        return pd.DataFrame(columns=["date", "value"])

    col = next((c for c in candidates if c in df.columns), None)
    if col is None:
        return pd.DataFrame(columns=["date", "value"])

    data = df[["date", col]].copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["value"] = pd.to_numeric(data[col], errors="coerce")
    return data.dropna(subset=["date", "value"])[["date", "value"]].sort_values("date")


def _spread_card(
    key: str,
    label: str,
    left_df: pd.DataFrame | None,
    left_candidates: list[str],
    right_df: pd.DataFrame | None,
    right_candidates: list[str],
    unit: str = "%",
) -> dict:
    left = _macro_series_frame(left_df, left_candidates)
    right = _macro_series_frame(right_df, right_candidates)
    if left.empty or right.empty:
        return _empty_macro_card(key, label, unit)

    merged = left.merge(right, on="date", how="inner", suffixes=("_left", "_right"))
    if merged.empty:
        return _empty_macro_card(key, label, unit)

    merged["spread"] = merged["value_left"] - merged["value_right"]
    return _macro_card(key, label, merged[["date", "spread"]], ["spread"], unit)


def _money_supply_spread_card(df: pd.DataFrame | None) -> dict:
    if df is None or len(df) == 0 or not {"M1_yoy", "M2_yoy"}.issubset(df.columns):
        return _empty_macro_card("m1_m2_spread", "M1-M2 Spread")

    data = df.copy()
    data["M1_yoy"] = pd.to_numeric(data["M1_yoy"], errors="coerce")
    data["M2_yoy"] = pd.to_numeric(data["M2_yoy"], errors="coerce")
    data["m1_m2_spread"] = data["M1_yoy"] - data["M2_yoy"]
    return _macro_card("m1_m2_spread", "M1-M2 Spread", data, ["m1_m2_spread"])


def macro_cards() -> list[dict]:
    cpi = _load_macro("cpi")
    ppi = _load_macro("ppi")
    money_supply = _load_macro("money_supply")
    return [
        _macro_card("gdp", "GDP YoY", _load_macro("gdp"), ["gdp_yoy", "GDP_同比", "今值"]),
        _macro_card("pmi", "制造业 PMI", _load_macro("pmi"), ["pmi_mfg", "PMI010000", "今值"]),
        _macro_card("cpi", "CPI YoY", cpi, ["nt_yoy", "cpi_yoy", "CPI_全国_同比", "今值"]),
        _macro_card("shibor", "SHIBOR 7D", _load_macro("shibor"), ["1W", "1W-定价"]),
        _money_supply_spread_card(money_supply),
        _spread_card("ppi_cpi_spread", "PPI-CPI Spread", ppi, ["ppi_yoy"], cpi, ["nt_yoy", "cpi_yoy", "CPI_全国_同比", "今值"]),
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
        # HMM probability fields
        "regime_probs": getattr(snapshot, "regime_probs", {}),
        "detection_method": getattr(snapshot, "detection_method", "rule_based"),
        "hmm_confidence": round(getattr(snapshot, "hmm_confidence", 0.0), 4),
        "hmm_entropy": round(getattr(snapshot, "hmm_entropy", 0.0), 4),
        "decision_reason": getattr(snapshot, "decision_reason", ""),
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
    from data.ingestion.fetcher import get_index_daily

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
    from data.ingestion.fetcher import get_index_daily

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
