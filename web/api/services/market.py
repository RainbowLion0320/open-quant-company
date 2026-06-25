"""Market API domain service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from data.storage.datahub import get_datahub
from web.api.serializers import safe_float, series_card
from web.api.version import get_project_meta

HUB = get_datahub()

RANGE_TAIL = {"1D": 2, "1M": 22, "6M": 126, "YTD": 252}
CORE_INDEX_CARDS = [
    ("sse", "上证综指", "000001.SH", "sh000001", "上证综指 OHLCV"),
    ("csi300", "沪深300", "000300.SH", "sh000300", "沪深300指数 OHLCV"),
    ("chinext", "创业板指", "399006.SZ", "sz399006", "创业板指 OHLCV"),
    ("star50", "科创50", "000688.SH", "sh000688", "科创50指数 OHLCV"),
]
ASSET_PULSE_REPRESENTATIVES = {
    "stock": {"symbol": "000001.SH", "series_key": "sse", "unit": ""},
    "etf": {"symbol": "510300", "unit": ""},
    "bond": {"symbol": "CN10Y", "unit": ""},
    "futures": {"symbol": "IF", "unit": ""},
    "crypto": {"symbol": "BTC/USDT", "unit": "USDT"},
}
ETF_CATEGORY_LABELS = {
    "equity": "宽基/行业",
    "bond": "债券",
    "commodity": "黄金/商品",
    "qdi": "跨境",
    "cash": "货币",
}
FUTURES_CATEGORY_LABELS = {
    "equity_index": "股指",
    "bond": "国债",
    "commodity": "商品",
}
FUTURES_DISPLAY_SYMBOLS = {
    "IF": ("IF.CFX", "沪深300股指", "equity_index"),
    "IC": ("IC.CFX", "中证500股指", "equity_index"),
    "IM": ("IM.CFX", "中证1000股指", "equity_index"),
    "T": ("T.CFX", "10年国债期货", "bond"),
    "TF": ("TF.CFX", "5年国债期货", "bond"),
    "RB": ("RB", "螺纹钢", "commodity"),
    "AU": ("AU.SHF", "黄金期货", "commodity"),
    "CU": ("CU.SHF", "铜", "commodity"),
    "SC": ("SC.INE", "原油", "commodity"),
}
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


def _normalize_asset_price_frame(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "close"])
    data = df.copy()
    if "date" not in data.columns:
        data = data.reset_index()
    date_col = next((c for c in data.columns if str(c).lower() in {"date", "日期", "index", "trade_date"}), data.columns[0])
    close_col = next((c for c in ("close", "收盘", "price", "最新价") if c in data.columns), None)
    if close_col is None:
        numeric = [c for c in data.columns if c != date_col and pd.api.types.is_numeric_dtype(data[c])]
        close_col = numeric[0] if numeric else None
    if close_col is None:
        return pd.DataFrame(columns=["date", "close"])
    out = data[[date_col, close_col]].rename(columns={date_col: "date", close_col: "close"}).copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    return out.dropna(subset=["date", "close"]).sort_values("date")


def _local_asset_frame(asset_type: str, symbol: str) -> pd.DataFrame:
    """Read local asset daily cache only; Market overview must not fetch provider data."""
    try:
        path = HUB.asset_daily_path(asset_type, symbol)
        if not path.exists():
            return pd.DataFrame(columns=["date", "close"])
        return _normalize_asset_price_frame(HUB.read_parquet(path, default=pd.DataFrame()))
    except Exception:
        return pd.DataFrame(columns=["date", "close"])


def _read_parquet_frame(path: Path) -> pd.DataFrame:
    try:
        if not path.exists():
            return pd.DataFrame(columns=["date", "close"])
        return _normalize_asset_price_frame(HUB.read_parquet(path, default=pd.DataFrame()))
    except Exception:
        return pd.DataFrame(columns=["date", "close"])


def _fund_daily_frame(symbol: str) -> pd.DataFrame:
    candidates = [
        HUB.store_dir("fund") / "daily" / f"{symbol}.SH.parquet",
        HUB.store_dir("fund") / "daily" / f"{symbol}.SZ.parquet",
        HUB.asset_daily_path("etf", symbol),
    ]
    for path in candidates:
        frame = _read_parquet_frame(path)
        if not frame.empty:
            return frame
    return pd.DataFrame(columns=["date", "close"])


def _futures_daily_frame(symbol: str) -> pd.DataFrame:
    suffix_candidates = [
        symbol,
        f"{symbol}.CFX",
        f"{symbol}.SHF",
        f"{symbol}.DCE",
        f"{symbol}.INE",
    ]
    for candidate in suffix_candidates:
        frame = _read_parquet_frame(HUB.asset_daily_path("futures", candidate))
        if not frame.empty:
            return frame
    return pd.DataFrame(columns=["date", "close"])


def _change_pct(frame: pd.DataFrame, lookback: int = 22) -> float:
    if frame.empty or "close" not in frame.columns:
        return 0.0
    values = pd.to_numeric(frame["close"], errors="coerce").dropna()
    if len(values) < 2:
        return 0.0
    start = values.iloc[-min(lookback, len(values))]
    end = values.iloc[-1]
    if not start:
        return 0.0
    return round((float(end) / float(start) - 1.0) * 100.0, 2)


def _series_from_frame(frame: pd.DataFrame, limit: int = 42, value_col: str = "close") -> list[dict]:
    if frame.empty or value_col not in frame.columns:
        return []
    data = frame.tail(limit).copy()
    return [
        {"date": str(row["date"])[:10], "value": float(row[value_col])}
        for _, row in data.iterrows()
        if pd.notna(row.get(value_col))
    ]


def _asset_overview_by_type() -> dict[str, dict]:
    try:
        from data.market.assets.overview import asset_overview_items

        return {str(item.get("asset_type")): item for item in asset_overview_items()}
    except Exception:
        return {}


def _status_from_blockers(blockers: list[str], *, has_data: bool = True) -> str:
    if blockers:
        return "blocked" if not has_data else "watch"
    return "ready" if has_data else "missing"


def _etf_categories() -> list[dict]:
    try:
        from data.market.assets.etf import ETF_UNIVERSE, _classify_etf
    except Exception:
        return []
    counts: dict[str, int] = {}
    for symbol in ETF_UNIVERSE:
        key = _classify_etf(symbol)
        counts[key] = counts.get(key, 0) + 1
    return [
        {"key": key, "label": ETF_CATEGORY_LABELS.get(key, key), "count": count}
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _etf_module(overview: dict[str, dict], series_limit: int) -> dict:
    item = overview.get("etf", {})
    frame = _fund_daily_frame("510300")
    blockers = list(item.get("blockers") or [])
    if frame.empty:
        blockers = [*blockers, "missing_local_etf_daily"]
    return {
        "asset_type": "etf",
        "kind": "fund_rotation",
        "label": str(item.get("label") or "ETF基金"),
        "status": _status_from_blockers(blockers, has_data=not frame.empty),
        "headline": "资金与宽基轮动",
        "metrics": [
            {"key": "universe", "label": "ETF池", "value": int(safe_float(item.get("universe_size"), 0)), "unit": "只"},
            {"key": "change_1m", "label": "沪深300ETF 1M", "value": _change_pct(frame), "unit": "%"},
        ],
        "series": _series_from_frame(frame, series_limit),
        "categories": _etf_categories(),
        "items": [],
        "blockers": blockers,
        "source_detail": str(item.get("data_source_detail") or ""),
    }


def _bond_module(overview: dict[str, dict], series_limit: int) -> dict:
    item = overview.get("bond", {})
    blockers = list(item.get("blockers") or [])
    path = HUB.store_dir("bond") / "treasury_yields.parquet"
    curve: list[dict] = []
    series: list[dict] = []
    metrics: list[dict] = [{"key": "universe", "label": "债券池", "value": int(safe_float(item.get("universe_size"), 0)), "unit": "只"}]
    has_data = False
    try:
        df = HUB.read_parquet(path, default=pd.DataFrame()) if path.exists() else pd.DataFrame()
        if not df.empty:
            data = df.copy()
            if "date" not in data.columns:
                data = data.reset_index()
            date_col = "date" if "date" in data.columns else "日期"
            data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
            data = data.dropna(subset=[date_col]).sort_values(date_col)
            latest = data.iloc[-1]
            tenors = [
                ("2Y", "中国国债收益率2年"),
                ("5Y", "中国国债收益率5年"),
                ("10Y", "中国国债收益率10年"),
                ("30Y", "中国国债收益率30年"),
            ]
            for tenor, col in tenors:
                value = safe_float(latest.get(col), None)
                if value is not None:
                    curve.append({"tenor": tenor, "value": round(value, 4)})
            y10 = safe_float(latest.get("中国国债收益率10年"), None)
            y2 = safe_float(latest.get("中国国债收益率2年"), None)
            if y10 is not None:
                metrics.append({"key": "yield_10y", "label": "10Y", "value": round(y10, 4), "unit": "%"})
            if y10 is not None and y2 is not None:
                metrics.append({"key": "spread_10y2y", "label": "10Y-2Y", "value": round((y10 - y2) * 100, 1), "unit": "bp"})
            if "中国国债收益率10年" in data.columns:
                series = [
                    {"date": str(row[date_col])[:10], "value": float(row["中国国债收益率10年"])}
                    for _, row in data.tail(series_limit).iterrows()
                    if pd.notna(row.get("中国国债收益率10年"))
                ]
            has_data = bool(curve or series)
    except Exception:
        has_data = False
    if not has_data:
        blockers = [*blockers, "missing_treasury_yield_curve"]
    return {
        "asset_type": "bond",
        "kind": "rate_curve",
        "label": str(item.get("label") or "债券"),
        "status": _status_from_blockers(blockers, has_data=has_data),
        "headline": "防御与利率",
        "metrics": metrics,
        "series": series,
        "curve": curve,
        "items": [],
        "blockers": blockers,
        "source_detail": str(item.get("data_source_detail") or ""),
    }


def _futures_module(overview: dict[str, dict]) -> dict:
    item = overview.get("futures", {})
    blockers = list(item.get("blockers") or [])
    items: list[dict] = []
    group_changes: dict[str, list[float]] = {}
    for symbol, (_store_symbol, name, category) in FUTURES_DISPLAY_SYMBOLS.items():
        frame = _futures_daily_frame(symbol)
        if frame.empty:
            continue
        change = _change_pct(frame)
        latest = safe_float(frame.iloc[-1].get("close"), None)
        items.append({
            "symbol": symbol,
            "label": name,
            "category": category,
            "category_label": FUTURES_CATEGORY_LABELS.get(category, category),
            "value": latest,
            "change_pct": change,
        })
        group_changes.setdefault(category, []).append(change)
    groups = [
        {
            "key": key,
            "label": FUTURES_CATEGORY_LABELS.get(key, key),
            "value": round(sum(values) / len(values), 2) if values else 0.0,
            "count": len(values),
        }
        for key, values in group_changes.items()
    ]
    if not items:
        blockers = [*blockers, "missing_local_futures_daily"]
    movers = sorted(items, key=lambda row: abs(float(row.get("change_pct") or 0)), reverse=True)[:6]
    return {
        "asset_type": "futures",
        "kind": "contract_movers",
        "label": str(item.get("label") or "期货"),
        "status": _status_from_blockers(blockers, has_data=bool(items)),
        "headline": "风险传导与商品动量",
        "metrics": [
            {"key": "contracts", "label": "合约池", "value": int(safe_float(item.get("universe_size"), 0)), "unit": "个"},
            {"key": "local_contracts", "label": "本地样本", "value": len(items), "unit": "个"},
        ],
        "groups": sorted(groups, key=lambda row: row["key"]),
        "items": movers,
        "blockers": blockers,
        "source_detail": str(item.get("data_source_detail") or ""),
    }


def _crypto_module(overview: dict[str, dict]) -> dict:
    item = overview.get("crypto", {})
    blockers = list(item.get("blockers") or [])
    if "crypto_data_stale_until_fresh_source" not in blockers:
        blockers.append("crypto_data_stale_until_fresh_source")
    return {
        "asset_type": "crypto",
        "kind": "risk_sentinel",
        "label": str(item.get("label") or "加密货币"),
        "status": "blocked",
        "headline": "外部风险哨兵",
        "metrics": [
            {"key": "universe", "label": "观察池", "value": int(safe_float(item.get("universe_size"), 0)), "unit": "个"},
        ],
        "series": [],
        "items": [],
        "blockers": blockers,
        "source_detail": str(item.get("data_source_detail") or ""),
    }


def asset_market_modules(series_limit: int = 42) -> list[dict]:
    overview = _asset_overview_by_type()
    return [
        _etf_module(overview, series_limit),
        _bond_module(overview, series_limit),
        _futures_module(overview),
        _crypto_module(overview),
    ]


def _series_card_from_frame(
    *,
    key: str,
    label: str,
    symbol: str,
    df: pd.DataFrame,
    unit: str = "",
    data_source: str,
    source_detail: str,
    series_limit: int,
) -> dict:
    if df.empty:
        return {
            "key": key,
            "label": label,
            "symbol": symbol,
            "value": None,
            "change": 0.0,
            "change_pct": 0.0,
            "unit": unit,
            "series": [],
            "data_source": "missing",
            "source_detail": source_detail,
        }
    return series_card(
        key,
        label,
        symbol,
        df.tail(series_limit),
        "close",
        unit,
        data_source=data_source,
        source_detail=source_detail,
        series_limit=series_limit,
    )


def _readiness_score(item: dict) -> int:
    stages = ("data_status", "strategy_status", "backtest_status", "paper_status", "live_status")
    return sum(1 for stage in stages if str(item.get(stage) or "") in {"ready", "configured_contract", "conditional"})


def asset_pulse_cards(index_cards: list[dict], series_limit: int = 42) -> list[dict]:
    """Build legacy asset-class metadata cards for lightweight regime consumers."""
    try:
        from data.market.assets.overview import asset_overview_items

        overview_items = asset_overview_items()
    except Exception:
        overview_items = []

    index_by_key = {card.get("key"): card for card in index_cards}
    cards: list[dict] = []
    for item in overview_items:
        asset_type = str(item.get("asset_type") or "")
        rep = ASSET_PULSE_REPRESENTATIVES.get(asset_type, {})
        symbol = str(rep.get("symbol") or "")
        if asset_type == "stock" and index_by_key.get("sse"):
            base = dict(index_by_key["sse"])
            base["key"] = "stock"
            base["label"] = item.get("label") or base.get("label") or "Stock"
            base["symbol"] = symbol or base.get("symbol", "")
        else:
            frame = _local_asset_frame(asset_type, symbol) if symbol else pd.DataFrame(columns=["date", "close"])
            base = _series_card_from_frame(
                key=asset_type,
                label=str(item.get("label") or asset_type),
                symbol=symbol,
                df=frame,
                unit=str(rep.get("unit") or ""),
                data_source=str(item.get("data_source") or "unknown"),
                source_detail=str(item.get("data_source_detail") or ""),
                series_limit=series_limit,
            )
        base.update({
            "asset_type": asset_type,
            "data_status": str(item.get("data_status") or "blocked"),
            "strategy_status": str(item.get("strategy_status") or "blocked"),
            "backtest_status": str(item.get("backtest_status") or "blocked"),
            "paper_status": str(item.get("paper_status") or "blocked"),
            "live_status": str(item.get("live_status") or "blocked"),
            "live_adapter": str(item.get("live_adapter") or ""),
            "blockers": list(item.get("blockers") or []),
            "universe_size": int(safe_float(item.get("universe_size"), 0)),
            "readiness_score": _readiness_score(item),
        })
        cards.append(base)
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

    index_cards = multi_asset_cards(bench)
    return {
        "regime": regime_payload(snapshot),
        "multi_asset": index_cards,
        "asset_pulse": asset_pulse_cards(index_cards),
        "asset_modules": asset_market_modules(),
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
    max_positions = orch.params.get("max_positions", 0)
    index_cards = multi_asset_cards(recent, series_limit=tail)
    pulse_cards = asset_pulse_cards(index_cards, series_limit=min(tail, 64))

    return {
        "regime": regime_payload(snapshot),
        "kline": kline_series(recent),
        "range": range_key,
        "multi_asset": index_cards,
        "asset_pulse": pulse_cards,
        "asset_modules": asset_market_modules(series_limit=min(tail, 64)),
        "freshness": {
            "market": str(recent.iloc[-1]["date"])[:10] if len(recent) else "",
            "assets": str(recent.iloc[-1]["date"])[:10] if len(recent) else "",
        },
        "pool_size": max_positions,
        "position_capacity": position_capacity(max_positions),
        "config": {"project": get_project_meta()},
        "updated": datetime.now().strftime("%H:%M"),
    }
