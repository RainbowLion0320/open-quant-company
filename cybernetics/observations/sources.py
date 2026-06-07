"""Market observation data source helpers."""
from __future__ import annotations

from typing import Optional, Sequence, Any

from cybernetics.regime_scoring import clamp as _score_clamp

def _get_regime_indexes() -> list[tuple]:
    """Read regime index weights from config, fallback to defaults."""
    from core.settings import get_section
    cfg = get_section("cybernetics.regime_indexes", {}) or {}
    _INDEX_NAMES = {
        "sh000001": "上证综指", "sh000300": "沪深300",
        "sz399001": "深证成指", "sz399006": "创业板指", "sh000905": "中证500",
    }
    defaults = {"sh000001": 0.25, "sh000300": 0.25, "sz399001": 0.20, "sz399006": 0.15, "sh000905": 0.15}
    merged = {**defaults, **cfg}
    return [(k, _INDEX_NAMES.get(k, k), v) for k, v in merged.items()]


# Current config is read on each detection so Config Center changes apply
# without restarting the API.
_REGIME_INDEXES: list[tuple] | None = None

def _regime_indexes() -> list[tuple]:
    return _get_regime_indexes()

def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return _score_clamp(value, lower, upper)

def _frame_close_volume(df):
    """Return a sorted OHLCV-like frame with numeric close/volume columns."""
    import pandas as pd

    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["date", "close", "volume"])

    data = df.copy()
    data.columns = [str(c).lower() for c in data.columns]
    if "close" not in data.columns and "收盘" in df.columns:
        data["close"] = df["收盘"]
    if "volume" not in data.columns and "成交量" in df.columns:
        data["volume"] = df["成交量"]

    if "date" in data.columns:
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data = data.dropna(subset=["date"]).sort_values("date")
    elif data.index.name:
        data = data.reset_index().rename(columns={data.index.name: "date"})
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        data = data.dropna(subset=["date"]).sort_values("date")

    data["close"] = pd.to_numeric(data.get("close"), errors="coerce")
    if "volume" in data.columns:
        data["volume"] = pd.to_numeric(data["volume"], errors="coerce")
    return data.dropna(subset=["close"]).reset_index(drop=True)

def _stock_daily_files() -> list:
    from data.storage.datahub import get_datahub

    daily_dir = get_datahub().store_path("stock") / "daily"
    if not daily_dir.exists():
        return []
    return sorted(daily_dir.glob("*.parquet"))

def _stock_daily_source_sql(files: Optional[Sequence[Any]] = None) -> Optional[str]:
    if files is None:
        from data.storage.datahub import get_datahub

        daily_dir = get_datahub().store_path("stock") / "daily"
        if not daily_dir.exists():
            return None
        return "'" + str(daily_dir / "*.parquet").replace("'", "''") + "'"

    paths = [str(path).replace("'", "''") for path in files]
    if not paths:
        return None
    return "[" + ", ".join(f"'{path}'" for path in paths) + "]"
