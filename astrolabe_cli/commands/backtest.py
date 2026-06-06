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


def check() -> CliResult:
    """Run backtest quality checks: reproducibility, PIT, production pipeline contracts."""
    import subprocess as sp

    checks = {}
    all_ok = True

    for name, test_path in [
        ("reproducibility", "tests/test_backtest_reproducibility.py"),
        ("pit", "tests/test_backtest_pit_contracts.py"),
        ("pipeline_contract", "tests/test_backtest_pipeline_runner_contracts.py"),
    ]:
        result = sp.run(
            [sys.executable, "-m", "pytest", test_path, "-q", "--tb=no"],
            capture_output=True, text=True,
        )
        passed = result.returncode == 0
        checks[name] = {"ok": passed}
        if not passed:
            all_ok = False

    return CliResult(
        ok=all_ok,
        command="backtest check",
        message="All backtest checks passed" if all_ok else "Some backtest checks failed",
        data=checks,
        errors=[k for k, v in checks.items() if not v["ok"]],
    )
