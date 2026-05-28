from __future__ import annotations

import subprocess
import sys

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload


def status() -> CliResult:
    from cybernetics.orchestrator import QuantOrchestrator

    snapshot = QuantOrchestrator().detect()
    regime = snapshot.regime.value if hasattr(snapshot.regime, "value") else str(snapshot.regime)
    return CliResult(
        ok=True,
        command="regime status",
        message=f"Regime: {regime}",
        data={
            "regime": regime,
            "score": float(getattr(snapshot, "regime_score", 0.0)),
            "trend": str(getattr(snapshot, "index_ma_trend", "")),
        },
    )


def train_profit(dry_run: bool) -> CliResult:
    cmd = [sys.executable, "scripts/train_market_regime_profit.py"]
    if dry_run:
        return CliResult(
            ok=True,
            command="regime train-profit",
            message="Dry run: train Market Regime profit policy",
            data=dry_run_payload("regime.train_profit", cmd=cmd),
        )
    completed = subprocess.run(cmd, capture_output=True, text=True)
    return CliResult(
        ok=completed.returncode == 0,
        command="regime train-profit",
        message="Regime profit training finished" if completed.returncode == 0 else "Regime profit training failed",
        data={"returncode": completed.returncode},
        errors=[completed.stderr.strip()] if completed.returncode else [],
    )
