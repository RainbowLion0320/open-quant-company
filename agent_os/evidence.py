from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from agent_os.ledger import AgentLedger


FILE_EVIDENCE_KINDS = {"artifact", "file", "code", "report", "ledger"}


def hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


class EvidenceResolver:
    def __init__(self, ledger: AgentLedger | None = None):
        self.ledger = ledger or AgentLedger()

    def resolve(self, evidence_id: str) -> dict[str, Any]:
        evidence = self.ledger.get_evidence(evidence_id)
        if not evidence:
            return {
                "status": "missing_evidence",
                "evidence_id": evidence_id,
                "evidence": None,
                "navigation": None,
            }

        status = evidence.get("freshness_status") or "unknown"
        if evidence.get("kind") in FILE_EVIDENCE_KINDS:
            path = Path(str(evidence.get("uri") or ""))
            if not path.exists():
                return {"status": "missing_evidence", "evidence_id": evidence_id, "evidence": evidence, "navigation": None}
            evidence = {**evidence, "hash": hash_file(path)}
            status = "fresh"

        return {
            "status": status,
            "evidence_id": evidence_id,
            "evidence": evidence,
            "navigation": _navigation_for_evidence(evidence),
        }


def _navigation_for_evidence(evidence: dict[str, Any]) -> dict[str, str] | None:
    kind = str(evidence.get("kind") or "")
    uri = str(evidence.get("uri") or "").strip()
    if kind != "web_route" or not _is_safe_local_route(uri):
        return None
    return {
        "kind": "web_route",
        "href": uri,
        "label": str(evidence.get("label") or uri),
    }


def _is_safe_local_route(uri: str) -> bool:
    if not uri.startswith("/"):
        return False
    if uri.startswith("//"):
        return False
    return "\\" not in uri
