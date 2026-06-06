"""Execution CLI commands — dry-run paper execution without mutating state."""
from __future__ import annotations

from astrolabe_cli.results import CliResult


def dry_run() -> CliResult:
    """Run paper execution dry-run: load signals, propose orders, check risk, return JSON."""
    warnings = []
    try:
        from data.storage.results_db import load_latest_signals
        signals = load_latest_signals()
        signals_loaded = len(signals) if signals else 0
    except Exception as exc:
        warnings.append(f"Signal load failed: {exc}")
        signals_loaded = 0

    data_freshness_ok = True
    gate = {"ok": True, "stale": [], "missing": []}
    try:
        from astrolabe_cli.commands.data import freshness_gate_from_health_check
        gate, _rows = freshness_gate_from_health_check()
        data_freshness_ok = gate.get("ok", True)
    except Exception as exc:
        warnings.append(f"Freshness gate unavailable: {exc}")

    orders_proposed = 0
    orders_rejected = 0
    risk_rejections = []

    if signals_loaded == 0:
        warnings.append("No signals loaded; no orders proposed")
    else:
        # Simulate order proposal
        orders_proposed = min(signals_loaded, 20)
        if not data_freshness_ok:
            orders_rejected = orders_proposed
            risk_rejections.append("data_freshness_gate_failed")
            warnings.append("Data freshness gate failed; all buy orders blocked")

    return CliResult(
        ok=True,
        command="execution dry-run",
        message="Execution dry-run complete",
        data={
            "ok": True,
            "signals_loaded": signals_loaded,
            "orders_proposed": orders_proposed,
            "orders_rejected": orders_rejected,
            "risk_rejections": risk_rejections,
            "cash_after": 1_000_000.0,
            "freshness_gate": gate,
            "warnings": warnings,
        },
    )
