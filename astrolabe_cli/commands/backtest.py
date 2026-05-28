from __future__ import annotations

import subprocess
import sys

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload


def run_backtest(strategy: str, dry_run: bool) -> CliResult:
    cmd = [sys.executable, "backtest/run_all_strategies.py"]
    if strategy:
        cmd.extend(["--strategy", strategy])
    if dry_run:
        return CliResult(True, "backtest run", data=dry_run_payload("backtest.run", cmd=cmd), message="Dry run")
    completed = subprocess.run(cmd, capture_output=True, text=True)
    return CliResult(
        ok=completed.returncode == 0,
        command="backtest run",
        message="Backtest finished" if completed.returncode == 0 else "Backtest failed",
        data={"returncode": completed.returncode},
        errors=[completed.stderr.strip()] if completed.returncode else [],
    )
