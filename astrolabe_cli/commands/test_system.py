from __future__ import annotations

import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import yaml

from astrolabe_cli.results import CliResult
from data.storage.datahub import get_datahub


def check(suite: str = "quick") -> CliResult:
    config = _load_config()
    suites = config.get("suites", {}) if isinstance(config, dict) else {}
    suite_cfg = suites.get(suite) or {}
    targets = [str(item) for item in suite_cfg.get("targets", []) or []]
    if not targets:
        return CliResult(
            ok=False,
            command="test check",
            message=f"Unknown or empty test suite: {suite}",
            data={"suite": suite},
            errors=["unknown_suite"],
        )

    command = [sys.executable, "-m", "pytest", *targets, "-q"]
    started = _utc_now()
    start = time.monotonic()
    completed = subprocess.run(command, capture_output=True, text=True)
    duration = time.monotonic() - start
    finished = _utc_now()

    payload = _build_payload(
        suite=suite,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
        started_at=started,
        finished_at=finished,
        duration_seconds=duration,
    )
    _write_artifact(payload)

    return CliResult(
        ok=payload["ok"],
        command="test check",
        message="Test suite passed" if payload["ok"] else "Test suite failed",
        data=payload,
        errors=[] if payload["ok"] else payload["failures"][:5] or [payload["status"]],
    )


def _load_config() -> dict[str, Any]:
    path = get_datahub().project_root / "config" / "test_system.yaml"
    if not path.exists():
        return {"suites": {}}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"suites": {}}


def _build_payload(
    *,
    suite: str,
    command: list[str],
    returncode: int,
    stdout: str,
    stderr: str,
    started_at: str,
    finished_at: str,
    duration_seconds: float,
) -> dict[str, Any]:
    totals = _parse_totals("\n".join([stdout, stderr]))
    ok = returncode == 0
    return {
        "run_id": f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}",
        "suite": suite,
        "status": "passed" if ok else "failed",
        "ok": ok,
        "returncode": returncode,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(duration_seconds, 3),
        "command": command,
        "totals": totals,
        "failures": _extract_failures(stdout, stderr),
        "warnings": _extract_warnings(stdout, stderr),
        "stdout_excerpt": _excerpt(stdout),
        "stderr_excerpt": _excerpt(stderr),
    }


def _parse_totals(text: str) -> dict[str, int]:
    totals = {"passed": 0, "failed": 0, "skipped": 0, "warnings": 0, "errors": 0}
    for count, raw_kind in re.findall(r"(\d+)\s+(passed|failed|skipped|warnings?|errors?)\b", text):
        kind = raw_kind.rstrip("s")
        if kind == "warning":
            kind = "warnings"
        elif kind == "error":
            kind = "errors"
        totals[kind] = int(count)
    totals["total"] = totals["passed"] + totals["failed"] + totals["skipped"] + totals["errors"]
    return totals


def _extract_failures(stdout: str, stderr: str) -> list[str]:
    lines = []
    for line in "\n".join([stdout, stderr]).splitlines():
        stripped = line.strip()
        if stripped.startswith(("FAILED ", "ERROR ")) or " - AssertionError" in stripped:
            lines.append(stripped)
    return lines[:20]


def _extract_warnings(stdout: str, stderr: str) -> list[str]:
    lines = []
    for line in "\n".join([stdout, stderr]).splitlines():
        stripped = line.strip()
        if "warning" in stripped.lower() and stripped:
            lines.append(stripped)
    return lines[:20]


def _write_artifact(payload: dict[str, Any]) -> None:
    hub = get_datahub()
    artifact_dir = hub.artifact_dir("tests")
    runs_dir = artifact_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    hub.write_json(payload, runs_dir / f"{payload['run_id']}.json", indent=2)
    hub.write_json(payload, artifact_dir / "latest.json", indent=2)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _excerpt(text: str, max_chars: int = 4000) -> str:
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]
