"""Read-only AST Intelligence artifact payloads."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.storage.datahub import get_datahub

RECOMMENDED_AST_COMMAND = "astroq architecture ast --json"


def ast_intelligence_payload() -> dict[str, Any]:
    path = ast_intelligence_artifact_path()
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return {
            "status": "no_artifact",
            "latest": None,
            "summary": _empty_summary(),
            "issues": [],
            "clone_groups": [],
            "graph": {"nodes": [], "links": []},
            "errors": [],
            "recommended_command": RECOMMENDED_AST_COMMAND,
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    payload = dict(payload)
    payload["latest"] = {"generated_at": payload.get("generated_at"), "artifact_path": path.as_posix()}
    payload["summary"] = {**_empty_summary(), **summary, "artifact_age_seconds": _artifact_age_seconds(payload)}
    payload["recommended_command"] = str(payload.get("recommended_command") or RECOMMENDED_AST_COMMAND)
    payload.setdefault("issues", [])
    payload.setdefault("clone_groups", [])
    payload.setdefault("graph", {"nodes": [], "links": []})
    payload.setdefault("errors", [])
    return payload


def ast_intelligence_artifact_path() -> Path:
    return get_datahub().artifact_dir("architecture") / "ast" / "latest.json"


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
        "file_count": 0,
        "unit_count": 0,
        "issue_count": 0,
        "clone_group_count": 0,
        "languages": {},
        "severity_counts": {},
        "duplicate_score": 0,
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
