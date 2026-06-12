"""Read-only lifecycle readiness artifact payloads."""

from __future__ import annotations

from typing import Any

from data.storage.datahub import get_datahub
from web.api.services.artifacts import artifact_age_seconds, read_json_artifact

RECOMMENDED_LIFECYCLE_COMMAND = "astroq lifecycle check --json"


def lifecycle_payload() -> dict[str, Any]:
    path = get_datahub().artifact_dir("lifecycle") / "latest.json"
    payload = read_json_artifact(path)
    if not isinstance(payload, dict):
        return {
            "status": "no_artifact",
            "latest": None,
            "checks": {},
            "blockers": [],
            "warnings": [],
            "recommended_command": RECOMMENDED_LIFECYCLE_COMMAND,
        }
    out = dict(payload)
    out["latest"] = {"generated_at": out.get("generated_at"), "artifact_path": path.as_posix()}
    out["artifact_age_seconds"] = artifact_age_seconds(out)
    out["recommended_command"] = str(out.get("recommended_command") or RECOMMENDED_LIFECYCLE_COMMAND)
    return out
