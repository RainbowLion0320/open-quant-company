from __future__ import annotations

from astrolabe_cli.ast_intelligence import collect_ast_intelligence, write_ast_intelligence_artifact
from astrolabe_cli.results import CliResult
from data.storage.datahub import get_datahub


def ast_check() -> CliResult:
    try:
        payload = collect_ast_intelligence(get_datahub().project_root)
    except RuntimeError as exc:
        return CliResult(
            ok=False,
            command="architecture ast",
            message="AST Intelligence scan failed",
            data={"status": "error"},
            errors=[str(exc)],
        )
    path = write_ast_intelligence_artifact(payload)
    graph = payload.get("graph", {}) if isinstance(payload.get("graph"), dict) else {}
    return CliResult(
        ok=payload.get("status") != "error",
        command="architecture ast",
        message="AST Intelligence artifact generated",
        data={
            "artifact_path": path.as_posix(),
            "status": payload.get("status"),
            "generated_at": payload.get("generated_at"),
            "recommended_command": payload.get("recommended_command"),
            "summary": payload.get("summary", {}),
            "graph": {
                "node_count": len(graph.get("nodes", []) or []),
                "link_count": len(graph.get("links", []) or []),
            },
        },
        errors=payload.get("errors", []) if payload.get("status") == "error" else [],
    )
