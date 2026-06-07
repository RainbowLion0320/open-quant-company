"""Risk-free rate curves for performance analytics.

This module intentionally has no fixed-rate fallback.  If the configured curve
cannot cover the requested dates, analytics must fail instead of reporting a
misleading Sharpe/alpha.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from core.settings import get_section
from data.storage.datahub import get_datahub


class RiskFreeRateDataError(RuntimeError):
    """Raised when required risk-free curve data is missing or stale."""


CURVE_COLUMNS: dict[tuple[str, str], str] = {
    ("CN", "2Y"): "中国国债收益率2年",
    ("CN", "5Y"): "中国国债收益率5年",
    ("CN", "10Y"): "中国国债收益率10年",
    ("CN", "30Y"): "中国国债收益率30年",
    ("US", "2Y"): "美国国债收益率2年",
    ("US", "5Y"): "美国国债收益率5年",
    ("US", "10Y"): "美国国债收益率10年",
    ("US", "30Y"): "美国国债收益率30年",
}


@dataclass(frozen=True)
class RiskFreeRateSpec:
    mode: str = "curve"
    source: str = "treasury_yields"
    market: str = "CN"
    tenor: str = "2Y"
    max_staleness_days: int = 10
    path: str = ""


def risk_free_spec_from_config(config: dict | None = None) -> RiskFreeRateSpec:
    if config is None:
        backtest_cfg = get_section("backtest", {}) or {}
        if isinstance(backtest_cfg, Mapping) and "risk_free_rate" in backtest_cfg:
            raise RiskFreeRateDataError("fixed backtest.risk_free_rate is not allowed")
        cfg = backtest_cfg.get("risk_free", {}) if isinstance(backtest_cfg, Mapping) else {}
    elif isinstance(config, Mapping) and "backtest" in config:
        backtest_cfg = config.get("backtest", {}) or {}
        if isinstance(backtest_cfg, Mapping) and "risk_free_rate" in backtest_cfg:
            raise RiskFreeRateDataError("fixed backtest.risk_free_rate is not allowed")
        cfg = backtest_cfg.get("risk_free", {}) if isinstance(backtest_cfg, Mapping) else {}
    else:
        cfg = config
    cfg = cfg or {}
    if "fallback_rate" in cfg or "fixed_rate" in cfg:
        raise RiskFreeRateDataError("fixed/fallback risk-free rates are not allowed")
    spec = RiskFreeRateSpec(
        mode=str(cfg.get("mode", "curve")),
        source=str(cfg.get("source", "treasury_yields")),
        market=str(cfg.get("market", "CN")).upper(),
        tenor=str(cfg.get("tenor", "2Y")).upper(),
        max_staleness_days=int(cfg.get("max_staleness_days", 10)),
        path=str(cfg.get("path", "") or ""),
    )
    if spec.mode != "curve":
        raise RiskFreeRateDataError(f"unsupported risk-free mode: {spec.mode}")
    return spec


class RiskFreeRateProvider:
    """Load and align annualized risk-free rates from a local curve file."""

    def __init__(
        self,
        *,
        source_path: str | Path | None = None,
        market: str = "CN",
        tenor: str = "2Y",
        max_staleness_days: int = 10,
    ):
        self.market = str(market).upper()
        self.tenor = str(tenor).upper()
        self.max_staleness_days = int(max_staleness_days)
        if source_path is None:
            hub = get_datahub()
            source_path = hub.store_dir("bond") / "treasury_yields.parquet"
        self.source_path = Path(source_path)

    @classmethod
    def from_config(cls, config: dict | None = None) -> "RiskFreeRateProvider":
        spec = risk_free_spec_from_config(config)
        source_path = spec.path or None
        if source_path is None and spec.source != "treasury_yields":
            raise RiskFreeRateDataError(f"unsupported risk-free source: {spec.source}")
        return cls(
            source_path=source_path,
            market=spec.market,
            tenor=spec.tenor,
            max_staleness_days=spec.max_staleness_days,
        )

    @property
    def curve_column(self) -> str:
        key = (self.market, self.tenor)
        if key not in CURVE_COLUMNS:
            available = ", ".join(f"{market}:{tenor}" for market, tenor in sorted(CURVE_COLUMNS))
            raise RiskFreeRateDataError(
                f"unsupported risk-free curve {self.market}:{self.tenor}; available={available}"
            )
        return CURVE_COLUMNS[key]

    def load_curve(self) -> pd.DataFrame:
        if not self.source_path.exists():
            raise RiskFreeRateDataError(f"risk-free curve file missing: {self.source_path}")
        frame = pd.read_parquet(self.source_path).reset_index(drop=True)
        if "日期" not in frame.columns:
            raise RiskFreeRateDataError(f"risk-free curve missing date column: {self.source_path}")
        col = self.curve_column
        if col not in frame.columns:
            raise RiskFreeRateDataError(f"risk-free curve missing column: {col}")
        out = frame[["日期", col]].copy()
        out["date"] = pd.to_datetime(out["日期"], errors="coerce").dt.normalize().astype("datetime64[ns]")
        out["annual_rate"] = pd.to_numeric(out[col], errors="coerce")
        out = out.dropna(subset=["date", "annual_rate"]).sort_values("date")
        if out.empty:
            raise RiskFreeRateDataError(f"risk-free curve has no usable rows for {self.market}:{self.tenor}")
        if out["annual_rate"].abs().median() > 1:
            out["annual_rate"] = out["annual_rate"] / 100.0
        return out[["date", "annual_rate"]].drop_duplicates("date", keep="last")

    def annualized_series(self, index: Iterable) -> pd.Series:
        if isinstance(index, pd.Index):
            raw_index = index
        else:
            raw_index = pd.Index(index)
        if pd.api.types.is_numeric_dtype(raw_index.dtype):
            raise RiskFreeRateDataError("risk-free curve alignment requires date-like return index")
        target_index = pd.DatetimeIndex(pd.to_datetime(raw_index, errors="coerce")).normalize().astype("datetime64[ns]")
        if target_index.hasnans:
            raise RiskFreeRateDataError("risk-free curve alignment requires valid date-like return index")
        if len(target_index) == 0:
            return pd.Series(dtype="float64", index=pd.DatetimeIndex([]), name="risk_free_annual")

        curve = self.load_curve()
        target = pd.DataFrame({"target_date": target_index.astype("datetime64[ns]")})
        curve = curve.copy()
        curve["date"] = pd.to_datetime(curve["date"]).astype("datetime64[ns]")
        aligned = pd.merge_asof(
            target.sort_values("target_date"),
            curve.rename(columns={"date": "curve_date"}),
            left_on="target_date",
            right_on="curve_date",
            direction="backward",
        )
        missing_mask = aligned["annual_rate"].isna()
        stale_days = (aligned["target_date"] - aligned["curve_date"]).dt.days
        stale_mask = stale_days.isna() | (stale_days > self.max_staleness_days)
        bad = aligned[missing_mask | stale_mask]
        if not bad.empty:
            sample = ", ".join(pd.to_datetime(bad["target_date"]).dt.strftime("%Y-%m-%d").head(5).tolist())
            raise RiskFreeRateDataError(
                f"risk-free curve missing/stale for {len(bad)} dates; sample={sample}; "
                f"market={self.market}, tenor={self.tenor}, max_staleness_days={self.max_staleness_days}"
            )
        values = aligned.set_index(target_index)["annual_rate"].astype(float)
        values.name = "risk_free_annual"
        if not np.isfinite(values.to_numpy()).all():
            raise RiskFreeRateDataError("risk-free curve contains non-finite aligned values")
        return values


def risk_free_series_for_index(index: Iterable, config: dict | None = None) -> pd.Series:
    return RiskFreeRateProvider.from_config(config).annualized_series(index)
