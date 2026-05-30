"""Strategy evaluation evidence contracts."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

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
        ic=0.03 if evaluation.baseline_win_rate >= 0.6 else 0.0,
        icir=0.4 if evaluation.baseline_win_rate >= 0.6 else 0.0,
    )
    return evaluate_promotion(metrics, target_status=target_status)


def strategy_evidence_dir() -> Path:
    from data.datahub import get_datahub

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
    target_status: str = "paper",
) -> dict[str, Any]:
    metric_src = metrics or {}
    oos_src = oos or {}
    baseline_src = baselines or {name: {} for name in required_baselines()}
    normalized_metrics = {
        "cagr": _metric_value(metric_src, "cagr", _metric_value(metric_src, "total_return", 0.0)),
        "sharpe": _metric_value(metric_src, "sharpe"),
        "max_drawdown": _metric_value(metric_src, "max_drawdown"),
        "turnover": _metric_value(metric_src, "turnover"),
        "trades": int(_metric_value(metric_src, "trades", _metric_value(metric_src, "trade_count", 0.0))),
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
        regime_coverage={k: 1.0 for k, v in _normalized_regime_breakdown(regime_breakdown).items() if v},
    )
    decision = promotion_ready(evaluation, target_status=target_status)
    return {
        "strategy": strategy,
        "status": status,
        "baselines": {name: dict(baseline_src.get(name, {})) for name in required_baselines()},
        "metrics": normalized_metrics,
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
        "promotion_decision": {
            "target_status": decision.target_status,
            "passed": decision.passed,
            "failed_rules": list(decision.failed_rules),
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


def list_evidence_artifacts(root: str | Path | None = None) -> list[dict]:
    """List all evidence artifacts without creating files."""
    evidence_dir = Path(root) if root is not None else strategy_evidence_dir()
    if not evidence_dir.exists():
        return []
    results = []
    for path in sorted(evidence_dir.glob("*.json")):
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
            pd_data = data.get("promotion_decision", {})
            entry["promotion_decision"] = "passed" if pd_data.get("passed") else "blocked"
            entry["oos_status"] = data.get("oos", {}).get("months", 0)
            entry["baseline_count"] = len(data.get("baselines", {}))
        except (json.JSONDecodeError, OSError) as e:
            entry["parse_error"] = str(e)
        results.append(entry)
    return results


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
    report = build_evidence_report(
        strategy=strategy,
        status=status,
        metrics=result,
        oos={"months": 0, "start": start, "end": end},
        cost_model={
            "commission": _metric_value(result, "commission", 0.00025),
            "slippage": _metric_value(result, "slippage", 0.001),
        },
    )
    return write_strategy_evidence_report(report, output_dir=output_dir)
