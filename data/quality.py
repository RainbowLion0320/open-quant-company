"""
Data Quality Gate — freshness SLA enforcement, completeness, consistency.

Prevents strategy scans from silently producing signals on stale data.
Integrates with DataRegistry (SLA definitions) and DataHub (path resolution).

Usage:
  from data.quality import DataQualityGate, pre_scan_gate

  gate = DataQualityGate()
  report = gate.check_dimension("ohlcv_daily", symbol="000001")
  ok, issues = pre_scan_gate()  # returns (passed: bool, reports: list[QualityReport])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional

import pandas as pd
import numpy as np

from data.datahub import get_datahub
from data.data_registry import DataDimension, FRESHNESS_SLA_BY_FREQ, get_registry

HUB = get_datahub()
REGISTRY = get_registry()


@dataclass
class QualityReport:
    dimension: str
    label: str
    status: str  # fresh | stale | missing | error | skipped
    health_score: float  # 0-100
    freshness_days: int | None
    sla_days: int | None
    row_count: int
    null_pct: float
    date_min: str
    date_max: str
    issues: list[str] = field(default_factory=list)

    @property
    def is_fresh(self) -> bool:
        return self.status == "fresh"

    @property
    def is_stale(self) -> bool:
        return self.status == "stale"


# Critical dimensions that MUST be fresh for strategy scans
CRITICAL_SCAN_DIMENSIONS = [
    "ohlcv_daily",
    "adj_factor",
    "financial_summary",
    "fina_indicator",
]


class DataQualityGate:
    """Check data dimensions against freshness SLA, completeness, and consistency."""

    def __init__(self, today: date | None = None, hub=None):
        self.today = today or date.today()
        self._registry = REGISTRY
        self._hub = hub or HUB

    def check_dimension(
        self,
        key: str,
        symbol: str | None = None,
        df_override: pd.DataFrame | None = None,
    ) -> QualityReport:
        dim = self._registry.get(key)
        if dim is None:
            return QualityReport(
                dimension=key, label=key, status="error",
                health_score=0, freshness_days=None, sla_days=None,
                row_count=0, null_pct=100, date_min="", date_max="",
                issues=[f"Unknown dimension: {key}"],
            )

        if not dim.enabled or dim.status == "planned":
            return QualityReport(
                dimension=key, label=dim.label, status="skipped",
                health_score=100, freshness_days=None, sla_days=None,
                row_count=0, null_pct=0, date_min="", date_max="",
                issues=[],
            )

        sla = dim.freshness_sla_days or FRESHNESS_SLA_BY_FREQ.get(dim.freq, 5)
        issues: list[str] = []

        # Load data
        df = df_override
        if df is None:
            try:
                if symbol and "{" in (dim.cache or ""):
                    path = self._hub.dimension_path(key, symbol=symbol)
                elif dim.cache:
                    path = self._hub.store_root / dim.cache
                else:
                    return QualityReport(
                        dimension=key, label=dim.label, status="error",
                        health_score=0, freshness_days=None, sla_days=sla,
                        row_count=0, null_pct=100, date_min="", date_max="",
                        issues=["No cache path configured"],
                    )

                if path.exists() and not path.is_dir():
                    df = self._hub.read_parquet(path, default=pd.DataFrame())
                elif path.is_dir():
                    files = self._hub.list_parquet(path)
                    if files:
                        df = pd.concat(
                            [pd.read_parquet(f) for f in files[:20]],
                            ignore_index=True,
                        )
                    else:
                        df = pd.DataFrame()
                else:
                    df = pd.DataFrame()
            except Exception as e:
                return QualityReport(
                    dimension=key, label=dim.label, status="error",
                    health_score=0, freshness_days=None, sla_days=sla,
                    row_count=0, null_pct=100, date_min="", date_max="",
                    issues=[f"Read error: {e}"],
                )

        if df is None or df.empty:
            return QualityReport(
                dimension=key, label=dim.label, status="missing",
                health_score=0, freshness_days=None, sla_days=sla,
                row_count=0, null_pct=100, date_min="", date_max="",
                issues=["No data found"],
            )

        # Completeness
        null_pct = float(df.isna().mean().mean() * 100) if len(df.columns) > 0 else 100.0
        if null_pct > 20:
            issues.append(f"High null ratio: {null_pct:.1f}%")

        # Consistency: check expected columns exist (minimal check)
        expected_cols = self._expected_columns(key)
        if expected_cols:
            missing_cols = [c for c in expected_cols if c not in df.columns]
            if missing_cols:
                issues.append(f"Missing columns: {missing_cols}")

        # Freshness
        date_col, date_min, date_max = self._find_date_range(df)
        freshness_days = None
        if date_max:
            try:
                max_date = datetime.strptime(date_max, "%Y-%m-%d").date()
                freshness_days = (self.today - max_date).days
            except (ValueError, TypeError):
                pass

        if freshness_days is not None and freshness_days > sla:
            issues.append(
                f"Stale: {freshness_days}d since last update (SLA: {sla}d)"
            )

        # Status
        if freshness_days is None and date_max:
            status = "fresh"  # has data, can't determine age
        elif freshness_days is None:
            status = "error"
        elif freshness_days <= sla:
            status = "fresh"
        else:
            status = "stale"

        # Health score: weighted average of freshness + completeness + consistency
        freshness_score = max(0, 100 - max(0, (freshness_days or 0) - sla) * 5)
        completeness_score = max(0, 100 - null_pct * 2)
        consistency_score = 100 if not (expected_cols and any(
            c not in df.columns for c in expected_cols
        )) else 50

        health_score = round(
            freshness_score * 0.5 + completeness_score * 0.3 + consistency_score * 0.2, 1
        )

        return QualityReport(
            dimension=key,
            label=dim.label,
            status=status,
            health_score=health_score,
            freshness_days=freshness_days,
            sla_days=sla,
            row_count=len(df),
            null_pct=round(null_pct, 2),
            date_min=date_min,
            date_max=date_max,
            issues=issues,
        )

    def check_critical(self, symbol: str | None = None) -> list[QualityReport]:
        """Check all available dimensions."""
        reports = []
        for dim in self._registry.get_available():
            try:
                reports.append(self.check_dimension(dim.key, symbol=symbol))
            except Exception as e:
                reports.append(QualityReport(
                    dimension=dim.key, label=dim.label, status="error",
                    health_score=0, freshness_days=None, sla_days=None,
                    row_count=0, null_pct=100, date_min="", date_max="",
                    issues=[f"Check failed: {e}"],
                ))
        return reports

    def pre_scan_check(
        self,
        required_dims: list[str] | None = None,
        symbol: str | None = None,
    ) -> tuple[bool, list[QualityReport]]:
        """Pre-flight check before strategy scan.

        Returns (passed, reports).  If passed=False, critical data is stale.
        """
        required = required_dims or CRITICAL_SCAN_DIMENSIONS
        reports = []
        all_fresh = True

        for key in required:
            report = self.check_dimension(key, symbol=symbol)
            reports.append(report)
            if report.status in ("stale", "missing", "error"):
                all_fresh = False

        return all_fresh, reports

    def summary_report(self) -> dict:
        """Aggregate quality summary across all dimensions."""
        reports = self.check_critical()
        fresh = sum(1 for r in reports if r.status == "fresh")
        stale = sum(1 for r in reports if r.status == "stale")
        missing = sum(1 for r in reports if r.status == "missing")
        error = sum(1 for r in reports if r.status == "error")
        skipped = sum(1 for r in reports if r.status == "skipped")

        scores = [r.health_score for r in reports if r.status not in ("skipped",)]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0

        worst = sorted(
            [r for r in reports if r.status in ("stale", "missing", "error")],
            key=lambda r: r.health_score,
        )[:5]

        return {
            "checked_at": self.today.isoformat(),
            "total_dimensions": len(reports),
            "fresh": fresh,
            "stale": stale,
            "missing": missing,
            "error": error,
            "skipped": skipped,
            "avg_health_score": avg_score,
            "all_critical_fresh": stale == 0 and missing == 0 and error == 0,
            "worst_offenders": [
                {
                    "dimension": r.dimension,
                    "label": r.label,
                    "status": r.status,
                    "health_score": r.health_score,
                    "freshness_days": r.freshness_days,
                    "sla_days": r.sla_days,
                    "issues": r.issues,
                }
                for r in worst
            ],
            "details": [
                {
                    "dimension": r.dimension,
                    "label": r.label,
                    "status": r.status,
                    "health_score": r.health_score,
                    "freshness_days": r.freshness_days,
                    "row_count": r.row_count,
                    "null_pct": r.null_pct,
                }
                for r in reports
            ],
        }

    def _find_date_range(self, df: pd.DataFrame) -> tuple[str, str, str]:
        _DATE_COLS = ("date", "trade_date", "ann_date", "end_date", "ts", "quarter")
        for col in df.columns:
            if str(col).lower() not in _DATE_COLS:
                continue
            try:
                series = pd.to_datetime(df[col], errors="coerce").dropna()
            except Exception:
                continue
            if not series.empty:
                return (
                    col,
                    series.min().date().isoformat(),
                    series.max().date().isoformat(),
                )
        return "", "", ""

    def _expected_columns(self, key: str) -> list[str] | None:
        SCHEMA_MAP: dict[str, list[str]] = {
            "ohlcv_daily": ["date", "open", "high", "low", "close", "volume"],
            "adj_factor": ["date", "adj_factor"],
            "financial_summary": ["date", "roe", "roa", "gross_margin", "net_margin", "eps", "bps"],
            "fina_indicator": ["ann_date", "end_date", "roe", "roa", "eps", "bps"],
            "valuation_daily": ["date", "pe", "pb", "ps", "total_mv"],
            "moneyflow_daily": ["date", "net_buy_amount", "net_sell_amount"],
        }
        return SCHEMA_MAP.get(key)


def pre_scan_gate(
    required_dims: list[str] | None = None,
    symbol: str | None = None,
    strict: bool = False,
    hub=None,
) -> tuple[bool, list[QualityReport]]:
    """Convenience function: run pre-scan quality gate.

    Args:
        required_dims: Dimensions to check. Defaults to CRITICAL_SCAN_DIMENSIONS.
        symbol: Optional single symbol for symbol-level checks.
        strict: If True, raise RuntimeError on gate failure. For cron safety.
        hub: Optional DataHub instance for testing.

    Returns:
        (passed, reports) tuple.
    """
    gate = DataQualityGate(hub=hub)
    passed, reports = gate.pre_scan_check(required_dims, symbol)

    if strict and not passed:
        stale_list = [r.dimension for r in reports if not r.is_fresh]
        raise RuntimeError(
            f"Pre-scan quality gate FAILED. Stale dimensions: {stale_list}. "
            f"Run repair or data refresh before scanning."
        )

    return passed, reports
