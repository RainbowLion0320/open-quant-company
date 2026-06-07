"""Read-only System Test Intelligence payloads."""

from __future__ import annotations

import fnmatch
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from data.storage.datahub import get_datahub

RECOMMENDED_COMMAND = "astroq test check --suite quick --json"
STALE_AFTER_SECONDS = 7 * 24 * 60 * 60


def tests_summary_payload() -> dict[str, Any]:
    latest = _read_latest()
    domains = _domain_rollup(latest)
    if latest is None:
        return {
            "status": "no_run",
            "latest": None,
            "summary": _empty_summary(),
            "domains": domains,
            "recommended_command": RECOMMENDED_COMMAND,
        }

    totals = _normalize_totals(latest.get("totals"))
    status = str(latest.get("status") or ("passed" if latest.get("ok") else "failed"))
    summary = {
        "total": totals["total"],
        "passed": totals["passed"],
        "failed": totals["failed"],
        "errors": totals["errors"],
        "skipped": totals["skipped"],
        "warnings": totals["warnings"],
        "pass_rate": totals["passed"] / totals["total"] if totals["total"] else 0.0,
        "duration_seconds": float(latest.get("duration_seconds") or 0),
        "stale": _is_stale(latest),
    }
    return {
        "status": status,
        "latest": latest,
        "summary": summary,
        "domains": domains,
        "recommended_command": RECOMMENDED_COMMAND,
    }


def tests_domains_payload() -> dict[str, Any]:
    latest = _read_latest()
    return {
        "domains": _domain_rollup(latest),
        "recommended_command": RECOMMENDED_COMMAND,
    }


def test_runs_payload(limit: int = 20) -> dict[str, Any]:
    runs_dir = _artifact_dir() / "runs"
    if not runs_dir.exists():
        return {"runs": [], "total": 0, "recommended_command": RECOMMENDED_COMMAND}

    runs = []
    for path in sorted(runs_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        payload = _read_json(path)
        if not isinstance(payload, dict):
            continue
        runs.append(_run_summary(payload))
        if len(runs) >= limit:
            break
    return {"runs": runs, "total": len(runs), "recommended_command": RECOMMENDED_COMMAND}


def load_test_system_config() -> dict[str, Any]:
    config_path = get_datahub().project_root / "config" / "test_system.yaml"
    if not config_path.exists():
        return {"suites": {}, "domains": []}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"suites": {}, "domains": []}


def test_artifact_dir() -> Path:
    return _artifact_dir()


def _artifact_dir() -> Path:
    return get_datahub().artifact_dir("tests")


def _read_latest() -> dict[str, Any] | None:
    payload = _read_json(_artifact_dir() / "latest.json")
    return payload if isinstance(payload, dict) else None


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _domain_rollup(latest: dict[str, Any] | None) -> list[dict[str, Any]]:
    config = load_test_system_config()
    test_files = _discover_test_files()
    run_files = _command_test_files(latest.get("command", []) if latest else [])
    failed_files = _failure_files(latest.get("failures", []) if latest else [])
    known_files: set[str] = set()
    domains = []

    for raw in config.get("domains", []) or []:
        patterns = [str(item) for item in raw.get("patterns", []) or []]
        files = sorted(path for path in test_files if _matches_any(path, patterns))
        known_files.update(files)
        run_count = _run_file_count(files, run_files)
        failed_count = sum(1 for path in failed_files if path in files)
        domains.append(_domain_payload(raw, files, run_count, failed_count, latest))

    unknown_files = sorted((set(test_files) | set(run_files) | set(failed_files)) - known_files)
    domains.append(_domain_payload(_unclassified_domain(), unknown_files, _run_file_count(unknown_files, run_files), sum(1 for path in failed_files if path in unknown_files), latest))
    return domains


def _domain_payload(raw: dict[str, Any], files: list[str], run_count: int, failed_count: int, latest: dict[str, Any] | None) -> dict[str, Any]:
    if latest is None or run_count == 0:
        last_status = "not_run"
    elif failed_count:
        last_status = "failed"
    else:
        last_status = "passed"
    return {
        "key": str(raw.get("key") or "unknown"),
        "label_zh": str(raw.get("label_zh") or raw.get("label_en") or raw.get("key") or "Unknown"),
        "label_en": str(raw.get("label_en") or raw.get("label_zh") or raw.get("key") or "Unknown"),
        "description_zh": str(raw.get("description_zh") or ""),
        "description_en": str(raw.get("description_en") or ""),
        "test_files": files,
        "test_count": len(files),
        "run_count": run_count,
        "failed_count": failed_count,
        "last_status": last_status,
        "modules": [str(item) for item in raw.get("modules", []) or []],
        "specs": [str(item) for item in raw.get("specs", []) or []],
    }


def _discover_test_files() -> list[str]:
    root = get_datahub().project_root / "tests"
    if not root.exists():
        return []
    return sorted(path.relative_to(get_datahub().project_root).as_posix() for path in root.glob("test*.py"))


def _matches_any(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _command_test_files(command: list[Any]) -> set[str]:
    files = {str(item) for item in command if isinstance(item, str) and item.startswith("tests/") and item.endswith(".py")}
    if any(item == "tests" for item in command):
        files.update(_discover_test_files())
    return files


def _failure_files(failures: list[Any]) -> set[str]:
    files = set()
    for raw in failures:
        text = str(raw)
        for token in text.replace("::", " ").split():
            if token.startswith("tests/") and token.endswith(".py"):
                files.add(token)
            elif token.startswith("tests/") and ".py" in token:
                files.add(token.split(".py", 1)[0] + ".py")
    return files


def _run_file_count(files: list[str], run_files: set[str]) -> int:
    return sum(1 for path in files if path in run_files)


def _normalize_totals(raw: Any) -> dict[str, int]:
    raw = raw if isinstance(raw, dict) else {}
    totals = {key: int(raw.get(key) or 0) for key in ("passed", "failed", "skipped", "warnings", "errors")}
    totals["total"] = int(raw.get("total") or totals["passed"] + totals["failed"] + totals["skipped"] + totals["errors"])
    return totals


def _empty_summary() -> dict[str, Any]:
    return {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "warnings": 0,
        "pass_rate": 0.0,
        "duration_seconds": 0.0,
        "stale": False,
    }


def _run_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": payload.get("run_id", ""),
        "suite": payload.get("suite", ""),
        "status": payload.get("status", ""),
        "ok": bool(payload.get("ok")),
        "started_at": payload.get("started_at", ""),
        "finished_at": payload.get("finished_at", ""),
        "duration_seconds": float(payload.get("duration_seconds") or 0),
        "totals": _normalize_totals(payload.get("totals")),
    }


def _is_stale(payload: dict[str, Any]) -> bool:
    finished = str(payload.get("finished_at") or "")
    try:
        dt = datetime.fromisoformat(finished.replace("Z", "+00:00"))
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - dt).total_seconds() > STALE_AFTER_SECONDS


def _unclassified_domain() -> dict[str, Any]:
    return {
        "key": "unclassified",
        "label_zh": "未分类",
        "label_en": "Unclassified",
        "description_zh": "尚未映射到业务域的测试文件",
        "description_en": "Test files not yet mapped to a business domain",
        "modules": [],
        "specs": [],
    }
