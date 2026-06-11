"""Fair strategy competition from canonical backtest artifacts."""
from __future__ import annotations

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backtest.analytics import RiskAnalytics
from core.settings import get_section
from data.rates.risk_free_rates import risk_free_series_for_index
from data.storage.datahub import get_datahub
from data.strategy.catalog import get_enabled_strategies
from research.strategy_governance import default_strategy_roles


DEFAULT_OOS_MONTHS = 36


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    if not np.isfinite(out):
        return default
    return out


def _as_series(value: Any) -> pd.Series:
    if isinstance(value, pd.Series):
        out = value.copy()
    else:
        out = pd.Series(dtype=float)
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, errors="coerce")
    out = pd.to_numeric(out, errors="coerce")
    return out.dropna().sort_index()


def _trade_value(trade: Any) -> float:
    try:
        return abs(float(trade[3]) * float(trade[4]))
    except Exception:
        return 0.0


def _trade_date(trade: Any) -> pd.Timestamp | None:
    try:
        return pd.Timestamp(trade[0]).normalize()
    except Exception:
        return None


def _slice_trades(trades: list[Any], start: pd.Timestamp, end: pd.Timestamp) -> list[Any]:
    selected: list[Any] = []
    for trade in trades:
        dt = _trade_date(trade)
        if dt is not None and start.normalize() <= dt <= end.normalize():
            selected.append(trade)
    return selected


def _period_metrics(
    daily_returns: pd.Series,
    benchmark_returns: pd.Series,
    trades: list[Any],
    initial_cash: float,
) -> dict[str, Any]:
    returns = _as_series(daily_returns)
    benchmark = _as_series(benchmark_returns)
    if returns.empty:
        return {
            "n_trading_days": 0,
            "months": 0,
            "trade_count": 0,
            "turnover": 0.0,
            "error": "empty_returns",
        }

    aligned = pd.concat([returns.rename("strategy"), benchmark.rename("benchmark")], axis=1, join="inner").dropna()
    if aligned.empty:
        aligned = pd.DataFrame({"strategy": returns})
        aligned["benchmark"] = 0.0
    rf = risk_free_series_for_index(aligned.index)
    strategy_report = RiskAnalytics.compute(aligned["strategy"], aligned["benchmark"], risk_free_rates=rf)
    bench_report = RiskAnalytics.compute(aligned["benchmark"], aligned["benchmark"], risk_free_rates=rf)
    start = aligned.index.min()
    end = aligned.index.max()
    period_trades = _slice_trades(trades, start, end)
    years = max(len(aligned) / 252.0, 1 / 252.0)
    turnover = sum(_trade_value(trade) for trade in period_trades) / max(initial_cash * years, 1.0)
    return {
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "n_trading_days": int(strategy_report.n_trading_days),
        "months": int(aligned.index.to_period("M").nunique()),
        "total_return": _safe_float(strategy_report.total_return),
        "annual_return": _safe_float(strategy_report.annual_return),
        "sharpe": _safe_float(strategy_report.sharpe),
        "sortino": _safe_float(strategy_report.sortino),
        "calmar": _safe_float(strategy_report.calmar),
        "max_drawdown": _safe_float(strategy_report.max_drawdown),
        "volatility": _safe_float(strategy_report.volatility),
        "win_rate": _safe_float(strategy_report.win_rate),
        "information_ratio": _safe_float(strategy_report.information_ratio),
        "excess_return": _safe_float(strategy_report.annual_return - bench_report.annual_return),
        "benchmark_total_return": _safe_float(bench_report.total_return),
        "benchmark_annual_return": _safe_float(bench_report.annual_return),
        "benchmark_max_drawdown": _safe_float(bench_report.max_drawdown),
        "trade_count": len(period_trades),
        "turnover": _safe_float(turnover),
        "risk_free_mean": _safe_float(strategy_report.risk_free_mean),
    }


def summarize_backtest_result(result: dict[str, Any], *, oos_months: int = DEFAULT_OOS_MONTHS) -> dict[str, Any]:
    """Summarize one strategy backtest with a shared OOS window."""
    daily_returns = _as_series(result.get("daily_returns"))
    benchmark_returns = _as_series(result.get("bench_returns"))
    trades = list(result.get("trade_log") or [])
    initial_cash = _safe_float((get_section("backtest", {}) or {}).get("initial_cash"), 1_000_000.0)
    if daily_returns.empty:
        return {
            "full": {"error": "empty_returns", "n_trading_days": 0},
            "oos": {"error": "empty_returns", "n_trading_days": 0, "months": 0},
        }

    full = _period_metrics(daily_returns, benchmark_returns, trades, initial_cash)
    oos_start = daily_returns.index.max() - pd.DateOffset(months=oos_months)
    oos_returns = daily_returns[daily_returns.index > oos_start]
    oos_benchmark = benchmark_returns.reindex(oos_returns.index).dropna()
    oos = _period_metrics(oos_returns, oos_benchmark, trades, initial_cash)
    return {"full": full, "oos": oos}


def _catalog_by_name() -> dict[str, dict]:
    return {str(item["name"]): dict(item) for item in get_enabled_strategies()}


def _strategy_layer(name: str, item: dict[str, Any]) -> str:
    roles = default_strategy_roles()
    if name in roles:
        return roles[name].layer
    return str(item.get("layer") or item.get("strategy_type") or "candidate_alpha")


def _rank_score(oos: dict[str, Any], layer: str) -> float:
    drawdown_penalty = abs(_safe_float(oos.get("max_drawdown"))) * 60.0
    turnover_penalty = max(_safe_float(oos.get("turnover")) - 6.0, 0.0) * 2.0
    role_bonus = 5.0 if layer == "risk_overlay" and _safe_float(oos.get("max_drawdown")) > _safe_float(oos.get("benchmark_max_drawdown")) else 0.0
    return (
        _safe_float(oos.get("sharpe")) * 100.0
        + _safe_float(oos.get("annual_return")) * 100.0
        + _safe_float(oos.get("excess_return")) * 80.0
        - drawdown_penalty
        - turnover_penalty
        + role_bonus
    )


def _production_blockers(oos: dict[str, Any], *, layer: str, alpha_ic: float | None, alpha_icir: float | None) -> list[str]:
    blockers: list[str] = []
    if int(oos.get("months", 0) or 0) < 36:
        blockers.append("oos_months")
    if int(oos.get("trade_count", 0) or 0) < 36:
        blockers.append("trades")
    if _safe_float(oos.get("sharpe")) < 0.70:
        blockers.append("sharpe")
    if abs(_safe_float(oos.get("max_drawdown"))) > 0.20:
        blockers.append("max_drawdown")
    if _safe_float(oos.get("turnover")) > 4.0:
        blockers.append("turnover")
    if _safe_float(oos.get("excess_return")) <= 0:
        blockers.append("benchmark_excess")
    if layer == "risk_overlay":
        blockers.append("standalone_overlay_evidence")
    else:
        if alpha_ic is None or alpha_ic < 0.025:
            blockers.append("ic")
        if alpha_icir is None or alpha_icir < 0.35:
            blockers.append("icir")
    return blockers


def _paper_blockers(oos: dict[str, Any], *, layer: str) -> list[str]:
    blockers: list[str] = []
    if int(oos.get("months", 0) or 0) < 24:
        blockers.append("oos_months")
    if int(oos.get("trade_count", 0) or 0) < 24:
        blockers.append("trades")
    if _safe_float(oos.get("sharpe")) < 0.25:
        blockers.append("sharpe")
    if abs(_safe_float(oos.get("max_drawdown"))) > 0.25:
        blockers.append("max_drawdown")
    if _safe_float(oos.get("total_return")) <= 0:
        blockers.append("positive_oos_return")
    if layer == "risk_overlay":
        benchmark_dd = abs(_safe_float(oos.get("benchmark_max_drawdown")))
        strategy_dd = abs(_safe_float(oos.get("max_drawdown")))
        if benchmark_dd > 0 and strategy_dd > benchmark_dd * 0.85:
            blockers.append("drawdown_reduction")
    elif _safe_float(oos.get("excess_return")) <= 0:
        blockers.append("benchmark_excess")
    return blockers


def _decision(strategy: str, item: dict[str, Any], metrics: dict[str, Any]) -> dict[str, Any]:
    layer = _strategy_layer(strategy, item)
    oos = dict(metrics.get("oos") or {})
    alpha_ic = None
    alpha_icir = None
    production_blockers = _production_blockers(oos, layer=layer, alpha_ic=alpha_ic, alpha_icir=alpha_icir)
    paper_blockers = _paper_blockers(oos, layer=layer)
    if not production_blockers:
        recommended = "production"
    elif not paper_blockers:
        recommended = "paper"
    else:
        recommended = "candidate"

    warnings: list[str] = []
    if alpha_ic is None:
        warnings.append("missing_ic")
    if alpha_icir is None:
        warnings.append("missing_icir")
    if _safe_float(oos.get("turnover")) > 6.0:
        warnings.append("high_turnover")

    return {
        "strategy": strategy,
        "label": item.get("label", strategy),
        "previous_status": item.get("status", "candidate"),
        "recommended_status": recommended,
        "layer": layer,
        "rank_score": round(_rank_score(oos, layer), 6),
        "production_blockers": production_blockers,
        "paper_blockers": paper_blockers,
        "warnings": warnings,
        "alpha_evidence": {
            "ic": alpha_ic,
            "icir": alpha_icir,
            "status": "missing",
        },
        "metrics": metrics,
    }


def build_strategy_competition_report(
    *,
    backtest_dir: str | Path | None = None,
    oos_months: int = DEFAULT_OOS_MONTHS,
) -> dict[str, Any]:
    """Build a deterministic fair-competition report from backtest artifacts."""
    hub = get_datahub()
    artifact_dir = Path(backtest_dir) if backtest_dir is not None else hub.artifact_dir("backtests")
    catalog = _catalog_by_name()
    decisions: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for name, item in catalog.items():
        path = artifact_dir / f"backtest_{name}.pkl"
        if not path.exists():
            errors.append({"strategy": name, "error": "missing_backtest_artifact", "path": str(path)})
            decisions.append({
                "strategy": name,
                "label": item.get("label", name),
                "previous_status": item.get("status", "candidate"),
                "recommended_status": "candidate",
                "layer": _strategy_layer(name, item),
                "rank_score": -999999.0,
                "production_blockers": ["missing_backtest_artifact"],
                "paper_blockers": ["missing_backtest_artifact"],
                "warnings": [],
                "alpha_evidence": {"ic": None, "icir": None, "status": "missing"},
                "metrics": {},
            })
            continue
        try:
            with path.open("rb") as f:
                result = pickle.load(f)
            metrics = summarize_backtest_result(result, oos_months=oos_months)
            row = _decision(name, item, metrics)
            row["artifact"] = str(path)
            decisions.append(row)
        except Exception as exc:
            errors.append({"strategy": name, "error": str(exc), "path": str(path)})
            decisions.append({
                "strategy": name,
                "label": item.get("label", name),
                "previous_status": item.get("status", "candidate"),
                "recommended_status": "candidate",
                "layer": _strategy_layer(name, item),
                "rank_score": -999999.0,
                "production_blockers": ["metric_error"],
                "paper_blockers": ["metric_error"],
                "warnings": [],
                "alpha_evidence": {"ic": None, "icir": None, "status": "missing"},
                "metrics": {"error": str(exc)},
                "artifact": str(path),
            })

    decisions.sort(key=lambda row: _safe_float(row.get("rank_score"), -999999.0), reverse=True)
    for idx, row in enumerate(decisions, 1):
        row["rank"] = idx
    counts: dict[str, int] = {}
    previous_counts: dict[str, int] = {}
    for row in decisions:
        counts[row["recommended_status"]] = counts.get(row["recommended_status"], 0) + 1
        previous_counts[row["previous_status"]] = previous_counts.get(row["previous_status"], 0) + 1
    return {
        "schema_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": {
            "backtest_dir": str(artifact_dir),
            "oos_months": int(oos_months),
            "ranking_basis": "recent OOS risk-return from canonical PipelineBacktest artifacts",
        },
        "rules": {
            "production": {
                "min_oos_months": 36,
                "min_sharpe": 0.70,
                "max_drawdown": 0.20,
                "max_turnover": 4.0,
                "requires_positive_benchmark_excess": True,
                "requires_ic": True,
                "requires_icir": True,
            },
            "paper": {
                "min_oos_months": 24,
                "min_sharpe": 0.25,
                "max_drawdown": 0.25,
                "requires_positive_oos_return": True,
                "requires_positive_benchmark_excess": "alpha strategies",
                "requires_drawdown_reduction": "risk overlays",
            },
        },
        "summary": {
            "strategy_count": len(decisions),
            "error_count": len(errors),
            "recommended_counts": counts,
            "previous_counts": previous_counts,
            "production_count": counts.get("production", 0),
            "paper_count": counts.get("paper", 0),
        },
        "rankings": decisions,
        "errors": errors,
    }


def strategy_competition_dir() -> Path:
    return get_datahub().artifact_dir("tournaments")


def write_strategy_competition_report(
    *,
    backtest_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    oos_months: int = DEFAULT_OOS_MONTHS,
) -> tuple[dict[str, Any], Path]:
    report = build_strategy_competition_report(backtest_dir=backtest_dir, oos_months=oos_months)
    out_dir = Path(output_dir) if output_dir is not None else strategy_competition_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"strategy_competition_{stamp}.json"
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    latest = out_dir / "strategy_competition_latest.json"
    latest.write_text(text, encoding="utf-8")
    return report, path
