"""Strategy evaluation evidence contracts."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from research.strategy_catalog import catalog_items
from research.strategy_governance import StrategyMetrics, evaluate_promotion


def required_baselines() -> list[str]:
    return [
        "buy_and_hold",
        "fixed_weight",
        "ma_timing",
        "trend_only",
        "trend_breadth",
        "current_champion",
    ]


@dataclass(frozen=True)
class StrategyEvaluation:
    name: str
    cagr: float
    sharpe: float
    max_drawdown: float
    turnover: float
    oos_months: int
    trades: int
    baseline_win_rate: float = 0.0
    ic: float = 0.0
    icir: float = 0.0
    regime_coverage: dict[str, float] = field(default_factory=dict)
    cost_model: str = "commission_slippage"


def promotion_ready(evaluation: StrategyEvaluation, target_status: str = "paper"):
    metrics = StrategyMetrics(
        cagr=evaluation.cagr,
        sharpe=evaluation.sharpe,
        max_drawdown=evaluation.max_drawdown,
        turnover=evaluation.turnover,
        oos_months=evaluation.oos_months,
        trades=evaluation.trades,
        ic=evaluation.ic,
        icir=evaluation.icir,
    )
    return evaluate_promotion(metrics, target_status=target_status)


def strategy_evidence_dir() -> Path:
    from data.storage.datahub import get_datahub

    return get_datahub().store_path("research") / "strategy_evidence"


def _metric_value(metrics: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(metrics.get(key, default) or default)
    except Exception:
        return default


def _normalized_regime_breakdown(regime_breakdown: dict[str, Any] | None) -> dict[str, dict]:
    src = regime_breakdown or {}
    return {
        "bull": dict(src.get("bull", {})),
        "sideways": dict(src.get("sideways", {})),
        "bear": dict(src.get("bear", {})),
    }


def build_evidence_report(
    *,
    strategy: str,
    status: str,
    metrics: dict[str, Any] | None = None,
    baselines: dict[str, Any] | None = None,
    oos: dict[str, Any] | None = None,
    cost_model: dict[str, Any] | None = None,
    regime_breakdown: dict[str, Any] | None = None,
    alpha_evidence: dict[str, Any] | None = None,
    data_readiness: dict[str, Any] | None = None,
    backtest_evidence: dict[str, Any] | None = None,
    target_status: str = "paper",
) -> dict[str, Any]:
    metric_src = metrics or {}
    oos_src = oos or {}
    baseline_src = baselines or {name: {} for name in required_baselines()}
    missing_evidence = [
        key
        for key in ("ic", "icir")
        if key not in metric_src or metric_src.get(key) is None
    ]
    normalized_metrics = {
        "cagr": _metric_value(metric_src, "cagr", _metric_value(metric_src, "total_return", 0.0)),
        "sharpe": _metric_value(metric_src, "sharpe"),
        "max_drawdown": _metric_value(metric_src, "max_drawdown"),
        "turnover": _metric_value(metric_src, "turnover"),
        "trades": int(_metric_value(metric_src, "trades", _metric_value(metric_src, "trade_count", 0.0))),
        "win_rate": _metric_value(metric_src, "win_rate"),
        "benchmark_total_return": _metric_value(metric_src, "benchmark_total_return"),
        "excess_return": _metric_value(metric_src, "excess_return"),
    }
    if "ic" in metric_src and metric_src.get("ic") is not None:
        normalized_metrics["ic"] = _metric_value(metric_src, "ic")
    if "icir" in metric_src and metric_src.get("icir") is not None:
        normalized_metrics["icir"] = _metric_value(metric_src, "icir")
    alpha_src = dict(alpha_evidence or {})
    if not alpha_src:
        if missing_evidence:
            alpha_src = {
                "status": "missing",
                "reason": "missing_alpha_evidence",
                "ic": None,
                "icir": None,
            }
        else:
            alpha_src = {
                "status": "measured",
                "reason": "",
                "ic": normalized_metrics.get("ic"),
                "icir": normalized_metrics.get("icir"),
            }
    evaluation = StrategyEvaluation(
        name=strategy,
        cagr=normalized_metrics["cagr"],
        sharpe=normalized_metrics["sharpe"],
        max_drawdown=normalized_metrics["max_drawdown"],
        turnover=normalized_metrics["turnover"],
        oos_months=int(oos_src.get("months", 0) or 0),
        trades=normalized_metrics["trades"],
        baseline_win_rate=_metric_value(metric_src, "baseline_win_rate"),
        ic=_metric_value(normalized_metrics, "ic"),
        icir=_metric_value(normalized_metrics, "icir"),
        regime_coverage={k: 1.0 for k, v in _normalized_regime_breakdown(regime_breakdown).items() if v},
    )
    decision = promotion_ready(evaluation, target_status=target_status)
    failed_rules = list(decision.failed_rules)
    if missing_evidence:
        for key in missing_evidence:
            marker = f"missing_evidence:{key}"
            if marker not in failed_rules:
                failed_rules.append(marker)
    passed = decision.passed and not missing_evidence
    return {
        "strategy": strategy,
        "status": status,
        "baselines": {name: dict(baseline_src.get(name, {})) for name in required_baselines()},
        "metrics": normalized_metrics,
        "alpha_evidence": alpha_src,
        "data_readiness": dict(data_readiness or {"status": "unknown", "blockers": []}),
        "backtest_evidence": dict(backtest_evidence or {}),
        "oos": {
            "months": int(oos_src.get("months", 0) or 0),
            "start": str(oos_src.get("start", "")),
            "end": str(oos_src.get("end", "")),
        },
        "cost_model": {
            "commission": _metric_value(cost_model or {}, "commission", 0.00025),
            "slippage": _metric_value(cost_model or {}, "slippage", 0.001),
        },
        "regime_breakdown": _normalized_regime_breakdown(regime_breakdown),
        "missing_evidence": missing_evidence,
        "promotion_decision": {
            "target_status": decision.target_status,
            "passed": passed,
            "failed_rules": failed_rules,
            "warnings": list(decision.warnings),
            "rationale": decision.rationale,
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def write_strategy_evidence_report(report: dict[str, Any], output_dir: str | Path | None = None) -> Path:
    strategy = str(report.get("strategy", "")).strip()
    if not strategy or "/" in strategy or "\\" in strategy:
        raise ValueError(f"Invalid strategy for evidence report: {strategy!r}")
    out_dir = Path(output_dir) if output_dir is not None else strategy_evidence_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{strategy}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _catalog_strategy_names() -> list[str]:
    try:
        return [str(item.name) for item in catalog_items()]
    except Exception:
        return []


def _missing_evidence_entry(strategy: str, path: Path) -> dict:
    return {
        "strategy": strategy,
        "path": str(path),
        "updated": None,
        "exists": False,
        "promotion_decision": "missing",
        "oos_status": "missing",
        "baseline_count": 0,
        "parse_error": None,
    }


def _artifact_entry(path: Path) -> dict:
    strategy = path.stem
    entry = {
        "strategy": strategy,
        "path": str(path),
        "updated": None,
        "exists": True,
        "promotion_decision": None,
        "oos_status": None,
        "baseline_count": 0,
        "parse_error": None,
    }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entry["updated"] = data.get("generated_at")
        decision = data.get("promotion_decision", {})
        entry["promotion_decision"] = "passed" if decision.get("passed") else "blocked"
        months = int(data.get("oos", {}).get("months", 0) or 0)
        entry["oos_status"] = f"{months}m" if months > 0 else "missing"
        entry["baseline_count"] = len(data.get("baselines", {}))
    except (json.JSONDecodeError, OSError) as e:
        entry["promotion_decision"] = "parse_error"
        entry["oos_status"] = "unknown"
        entry["parse_error"] = str(e)
    return entry


def list_evidence_artifacts(root: str | Path | None = None) -> list[dict]:
    """List evidence status for every catalog strategy without creating files."""
    evidence_dir = Path(root) if root is not None else strategy_evidence_dir()
    catalog_names = _catalog_strategy_names()
    results: dict[str, dict] = {
        name: _missing_evidence_entry(name, evidence_dir / f"{name}.json")
        for name in catalog_names
    }
    if evidence_dir.exists():
        for path in sorted(evidence_dir.glob("*.json")):
            results[path.stem] = _artifact_entry(path)

    ordered = [results[name] for name in catalog_names if name in results]
    extras = [row for key, row in sorted(results.items()) if key not in set(catalog_names)]
    return ordered + extras


def load_evidence_artifact(strategy: str, root: str | Path | None = None) -> dict:
    """Load a single strategy's evidence artifact. Returns structured 'missing' if absent."""
    evidence_dir = Path(root) if root is not None else strategy_evidence_dir()
    path = evidence_dir / f"{strategy}.json"
    if not path.exists():
        return {
            "strategy": strategy,
            "exists": False,
            "path": str(path),
            "summary": {},
            "artifact": {},
            "parse_error": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "strategy": strategy,
            "exists": True,
            "path": str(path),
            "summary": {
                "status": data.get("status"),
                "promotion_decision": data.get("promotion_decision"),
                "generated_at": data.get("generated_at"),
            },
            "artifact": data,
            "parse_error": None,
        }
    except (json.JSONDecodeError, OSError) as e:
        return {
            "strategy": strategy,
            "exists": True,
            "path": str(path),
            "summary": {},
            "artifact": {},
            "parse_error": str(e),
        }


def write_backtest_evidence(
    strategy: str,
    status: str,
    result: dict[str, Any],
    *,
    start: str,
    end: str,
    output_dir: str | Path | None = None,
) -> Path:
    from research.strategy_competition import _alpha_evidence_from_result, summarize_backtest_result
    from research.strategy_governance import default_strategy_roles

    summary = summarize_backtest_result(result)
    oos_metrics = dict(summary.get("oos") or {})
    role = default_strategy_roles().get(strategy)
    layer = role.layer if role is not None else "candidate_alpha"
    alpha_evidence = _alpha_evidence_from_result(result, layer=layer)
    report_metrics = {
        "cagr": _metric_value(oos_metrics, "annual_return"),
        "total_return": _metric_value(oos_metrics, "total_return"),
        "sharpe": _metric_value(oos_metrics, "sharpe"),
        "max_drawdown": _metric_value(oos_metrics, "max_drawdown"),
        "turnover": _metric_value(oos_metrics, "turnover"),
        "trades": int(_metric_value(oos_metrics, "trade_count")),
        "win_rate": _metric_value(oos_metrics, "win_rate"),
        "benchmark_total_return": _metric_value(oos_metrics, "benchmark_total_return"),
        "excess_return": _metric_value(oos_metrics, "excess_return"),
    }
    if alpha_evidence.get("status") == "measured":
        report_metrics["ic"] = alpha_evidence.get("ic")
        report_metrics["icir"] = alpha_evidence.get("icir")
    score_panel = result.get("score_panel")
    score_panel_rows = int(len(score_panel)) if hasattr(score_panel, "__len__") else 0
    report = build_evidence_report(
        strategy=strategy,
        status=status,
        metrics=report_metrics,
        oos={
            "months": int(oos_metrics.get("months", 0) or 0),
            "start": str(oos_metrics.get("start", start)),
            "end": str(oos_metrics.get("end", end)),
        },
        cost_model={
            "commission": _metric_value(result, "commission", 0.00025),
            "slippage": _metric_value(result, "slippage", 0.001),
        },
        alpha_evidence=alpha_evidence,
        data_readiness={
            "status": "ok" if alpha_evidence.get("status") in {"measured", "not_applicable"} else "blocked",
            "blockers": [] if alpha_evidence.get("status") in {"measured", "not_applicable"} else [alpha_evidence.get("reason")],
        },
        backtest_evidence={
            "score_panel_rows": score_panel_rows,
            "has_score_panel": score_panel_rows > 0,
            "start": start,
            "end": end,
        },
    )
    return write_strategy_evidence_report(report, output_dir=output_dir)
