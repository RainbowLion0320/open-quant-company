"""Read-only AST Intelligence artifact payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from data.storage.datahub import get_datahub
from web.api.services.artifacts import artifact_age_seconds, read_json_artifact

RECOMMENDED_AST_COMMAND = "astroq architecture ast --json"


def ast_intelligence_payload() -> dict[str, Any]:
    path = ast_intelligence_artifact_path()
    payload = read_json_artifact(path)
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
    payload["summary"] = {**_empty_summary(), **summary, "artifact_age_seconds": artifact_age_seconds(payload)}
    payload["recommended_command"] = str(payload.get("recommended_command") or RECOMMENDED_AST_COMMAND)
    payload.setdefault("issues", [])
    payload.setdefault("clone_groups", [])
    payload.setdefault("graph", {"nodes": [], "links": []})
    payload.setdefault("errors", [])
    return payload


def ast_intelligence_artifact_path() -> Path:
    return get_datahub().artifact_dir("architecture") / "ast" / "latest.json"


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
