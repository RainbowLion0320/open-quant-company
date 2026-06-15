from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SemanticDraftPlanner:
    """Adapter for externally drafted semantic plans.

    The draft is treated as untrusted input. It is only a planner-shaped object;
    `agent_os.workflows` still applies the fixed-registry tool, desk-scope, and
    risk-level filters before any action is previewed or proposed.
    """

    def __init__(self, draft: dict[str, Any]):
        self._draft = dict(draft)

    def plan(
        self,
        *,
        desk: str,
        content: str,
        artifact_context: dict[str, Any],
        session_context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            **self._draft,
            "source": "semantic_draft",
            "request_context": {
                "desk": desk,
                "content_length": len(content),
                "artifact_context_seen": bool(artifact_context),
                "session_context_seen": bool(session_context),
            },
        }


def semantic_planner_from_payload(payload: dict[str, Any]) -> SemanticDraftPlanner | None:
    mode = str(payload.get("planner_mode") or "deterministic").strip()
    if mode in {"", "deterministic", "fixed_registry"}:
        return None
    if mode != "semantic_draft":
        raise ValueError(f"Unsupported planner_mode: {mode}")
    draft = payload.get("semantic_draft")
    if not isinstance(draft, dict):
        raise ValueError("planner_mode=semantic_draft requires semantic_draft object")
    return SemanticDraftPlanner(draft)


def semantic_planner_from_file(path: str | Path | None) -> SemanticDraftPlanner | None:
    if path is None or str(path).strip() == "":
        return None
    draft_path = Path(path).expanduser()
    try:
        raw = json.loads(draft_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Semantic draft file not found: {draft_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Semantic draft file is not valid JSON: {draft_path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Semantic draft file must contain a JSON object")
    return SemanticDraftPlanner(raw)
