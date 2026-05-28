from __future__ import annotations

import subprocess

from astrolabe_cli.results import CliResult


DRIFT_PATTERNS = (
    "34 维度|34维度|四维加权|多因子四维|9 页|9页|FastAPI（9|3页|3 页|5517|"
    "全局 ticker|底部 ticker|点位与日涨跌|Regime Score"
)


def check_docs() -> CliResult:
    cmd = [
        "rg",
        "-n",
        DRIFT_PATTERNS,
        "README.md",
        "CLAUDE.md",
        "docs",
        "wiki",
        "-g",
        "!docs/DOCUMENTATION.md",
        "-g",
        "!docs/development-plan.md",
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return CliResult(
            ok=False,
            command="docs check",
            message="ripgrep is required for docs drift check",
            data={"findings": [], "returncode": 127},
            errors=[str(exc)],
        )

    ok = completed.returncode in {0, 1}
    findings = [line for line in completed.stdout.splitlines() if line.strip()]
    return CliResult(
        ok=ok and not findings,
        command="docs check",
        message="No known stale phrases found" if not findings else "Known stale phrases found",
        data={"findings": findings, "returncode": completed.returncode},
        errors=[] if ok else [completed.stderr.strip()],
    )
