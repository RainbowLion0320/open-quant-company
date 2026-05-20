"""市场数据路由"""

from fastapi import APIRouter
from datetime import datetime
import pandas as pd
import yaml
from pathlib import Path

from data.datahub import get_datahub

router = APIRouter(prefix="/api/market", tags=["Market"])

ROOT = Path(__file__).resolve().parent.parent.parent.parent
HUB = get_datahub()


def _num(v, default=0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def _date_value_series(df: pd.DataFrame, value_col: str = "close", limit: int = 42) -> list[dict]:
    if df is None or len(df) == 0 or value_col not in df.columns:
        return []
    data = df.copy()
    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
    elif data.index.name:
        data = data.reset_index().rename(columns={data.index.name: "date"})
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
    else:
        data = data.reset_index().rename(columns={"index": "date"})
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date", value_col]).sort_values("date").tail(limit)
    return [{"date": str(r["date"])[:10], "value": round(_num(r[value_col]), 4)} for _, r in data.iterrows()]


def _series_card(key: str, label: str, symbol: str, df: pd.DataFrame | None, value_col: str = "close", unit: str = "") -> dict:
    series = _date_value_series(df, value_col=value_col)
    latest = series[-1]["value"] if series else None
    prev = series[-2]["value"] if len(series) > 1 else latest
    change = (latest - prev) if latest is not None and prev is not None else 0
    change_pct = (change / prev) if prev else 0
    return {
        "key": key,
        "label": label,
        "symbol": symbol,
        "value": latest,
        "change": round(change, 4),
        "change_pct": round(change_pct, 4),
        "unit": unit,
        "series": series,
    }


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
        "series": [{"date": str(r["date"])[:10], "value": round(_num(r[col]), 4)} for _, r in clean.iterrows()],
    }


def _multi_asset_cards(bench: pd.DataFrame) -> list[dict]:
    cards = [_series_card("ashare", "A股核心", "000001.SH", bench, "close", "")]

    gold = _load_etf("518880")
    cards.append(_series_card("gold", "黄金ETF", "518880.SH", gold, "close", ""))

    bond = _load_bond_yield()
    cards.append(_series_card("bond10y", "10Y国债", "CN10Y", bond, "中国国债收益率10年", "%"))

    shibor = _load_macro("shibor")
    cards.append(_series_card("cash", "资金利率", "SHIBOR 1W", shibor, "1W-定价", "%"))
    return cards


def _macro_cards() -> list[dict]:
    return [
        _macro_card("gdp", "GDP YoY", _load_macro("gdp"), ["gdp_yoy", "GDP_同比", "今值"]),
        _macro_card("pmi", "制造业 PMI", _load_macro("pmi"), ["pmi_mfg", "PMI010000", "今值"]),
        _macro_card("cpi", "CPI YoY", _load_macro("cpi"), ["nt_yoy", "cpi_yoy", "CPI_全国_同比", "今值"]),
        _macro_card("shibor", "SHIBOR 7D", _load_macro("shibor"), ["1W", "1W-定价"]),
    ]


def _strategy_matrix() -> list[dict]:
    try:
        from data.results_db import list_strategies, load_strategy_signals
    except Exception:
        return []

    rows = []
    for s in list_strategies():
        try:
            sigs = load_strategy_signals(s["name"], limit=1)
            top = sigs[0] if sigs else {}
        except Exception:
            top = {}
        rows.append({
            "name": s["name"],
            "label": s.get("label", s["name"]),
            "total": s.get("total", 0),
            "buys": s.get("buys", 0),
            "buy_ratio": round((s.get("buys", 0) / s.get("total", 1)) if s.get("total") else 0, 4),
            "score": round(_num(top.get("score")), 1) if top else 0,
            "signal": top.get("signal", "hold"),
            "top_symbol": top.get("symbol", ""),
            "top_name": top.get("name", ""),
            "industry": top.get("industry", ""),
            "last_computed": s.get("last_computed", ""),
        })
    return rows


def _alerts(regime: dict, macro: list[dict], multi_asset: list[dict], strategies: list[dict]) -> list[dict]:
    items = []
    items.append({
        "level": "success" if regime["value"] == "bull" else "warning" if regime["value"] == "sideways" else "danger",
        "title": f"市场状态: {regime['value']}",
        "detail": regime["ma_trend"],
        "time": datetime.now().strftime("%H:%M"),
    })
    gold = next((x for x in multi_asset if x["key"] == "gold"), None)
    if gold and abs(gold.get("change_pct") or 0) >= 0.01:
        items.append({
            "level": "success" if gold["change_pct"] > 0 else "danger",
            "title": "黄金ETF波动扩大",
            "detail": f"{gold['symbol']} {gold['change_pct'] * 100:+.2f}%",
            "time": datetime.now().strftime("%H:%M"),
        })
    pmi = next((x for x in macro if x["key"] == "pmi"), None)
    if pmi and pmi.get("value") is not None and pmi["value"] < 50:
        items.append({
            "level": "warning",
            "title": "制造业PMI低于荣枯线",
            "detail": f"最新 {pmi['value']:.1f}, 前值 {pmi['prev']:.1f}",
            "time": pmi.get("date", "")[-5:],
        })
    if strategies:
        best = max(strategies, key=lambda x: x.get("buy_ratio", 0))
        items.append({
            "level": "info",
            "title": "策略扫描完成",
            "detail": f"{best['label']} 买入占比 {best['buy_ratio'] * 100:.1f}%",
            "time": (best.get("last_computed") or "")[11:16],
        })
    return items[:6]


@router.get("")
async def market_overview():
    """市场总览: regime + K线 + 策略配置"""
    from cybernetics.orchestrator import QuantOrchestrator

    orch = QuantOrchestrator()
    snapshot = orch.detect()
    params = orch.get_params()

    from data.fetcher import get_index_daily
    bench = get_index_daily("sh000001")
    bench["date"] = pd.to_datetime(bench["date"])
    recent = bench.tail(120)

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

    config_path = ROOT / "config" / "settings.yaml"
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    from data.registry import get_enabled_strategies
    from data.symbols import CIRCLE_STOCKS

    regime = {
        "value": snapshot.regime.value,
        "ma_trend": snapshot.index_ma_trend,
        "volume_trend": snapshot.volume_trend,
        "breadth": round(snapshot.breadth, 2),
    }
    multi_asset = _multi_asset_cards(recent)
    macro = _macro_cards()
    strategy_matrix = _strategy_matrix()

    return {
        "regime": regime,
        "params": params,
        "kline": kline,
        "multi_asset": multi_asset,
        "macro": macro,
        "strategy_matrix": strategy_matrix,
        "alerts": _alerts(regime, macro, multi_asset, strategy_matrix),
        "freshness": {
            "market": str(recent.iloc[-1]["date"])[:10] if len(recent) else "",
            "macro": max([m.get("date", "") for m in macro] or [""]),
        },
        "config": {
            "project": cfg.get("project", {}),
            "buffett": cfg.get("buffett", {}),
            "cybernetics": cfg.get("cybernetics", {}),
            "multifactor": cfg.get("signals", {}).get("multifactor", {}),
            "backtest": cfg.get("backtest", {}),
            "trading": cfg.get("trading", {}),
        },
        "registry": get_enabled_strategies(),
        "pool_size": len(CIRCLE_STOCKS),
        "updated": datetime.now().strftime("%H:%M"),
    }
