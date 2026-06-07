"""Read-only Test Design Intelligence artifact payloads."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.storage.datahub import get_datahub

RECOMMENDED_DESIGN_COMMAND = "astroq test design --json"


def tests_design_payload() -> dict[str, Any]:
    path = _design_artifact_path()
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return {
            "status": "no_artifact",
            "latest": None,
            "summary": _empty_summary(),
            "matrix": {"kinds": [], "risks": []},
            "graph": {"nodes": [], "links": []},
            "cases": [],
            "smells": [],
            "recommended_command": RECOMMENDED_DESIGN_COMMAND,
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    payload = dict(payload)
    payload["latest"] = {"generated_at": payload.get("generated_at"), "artifact_path": path.as_posix()}
    payload["summary"] = {**_empty_summary(), **summary, "artifact_age_seconds": _artifact_age_seconds(payload)}
    payload["recommended_command"] = str(payload.get("recommended_command") or RECOMMENDED_DESIGN_COMMAND)
    return payload


def test_design_artifact_dir() -> Path:
    return _design_artifact_path().parent


def _design_artifact_path() -> Path:
    return get_datahub().artifact_dir("tests") / "design" / "latest.json"


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _empty_summary() -> dict[str, Any]:
    return {
        "test_count": 0,
        "file_count": 0,
        "target_count": 0,
        "spec_count": 0,
        "risk_count": 0,
        "risk_covered": 0,
        "risk_coverage_rate": 0.0,
        "target_link_rate": 0.0,
        "spec_link_rate": 0.0,
        "smell_count": 0,
        "severity_counts": {},
        "design_score": 0,
        "truncated": False,
        "artifact_age_seconds": None,
    }


def _artifact_age_seconds(payload: dict[str, Any]) -> float | None:
    generated_at = str(payload.get("generated_at") or "")
    if not generated_at:
        return None
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((datetime.now(timezone.utc) - dt).total_seconds(), 3)
