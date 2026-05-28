from __future__ import annotations

import subprocess
import sys

from astrolabe_cli.results import CliResult
from astrolabe_cli.safety import dry_run_payload


def build(dry_run: bool) -> CliResult:
    cmd = ["npm", "run", "build"]
    if dry_run:
        return CliResult(
            True,
            "web build",
            data=dry_run_payload("web.build", cmd=cmd, cwd="web/frontend"),
            message="Dry run",
        )
    completed = subprocess.run(cmd, cwd="web/frontend", capture_output=True, text=True)
    return CliResult(
        ok=completed.returncode == 0,
        command="web build",
        data={"returncode": completed.returncode},
        message="Web build finished" if completed.returncode == 0 else "Web build failed",
        errors=[completed.stderr.strip()] if completed.returncode else [],
    )


def serve(host: str, port: int) -> CliResult:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "web.api.app:create_app",
        "--factory",
        "--host",
        host,
        "--port",
        str(port),
    ]
    completed = subprocess.run(cmd)
    return CliResult(
        ok=completed.returncode == 0,
        command="web serve",
        data={"host": host, "port": port, "returncode": completed.returncode},
        message="Web server stopped",
    )
