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
                "snapshot": None,
                "navigation": None,
            }

        status = evidence.get("freshness_status") or "unknown"
        if evidence.get("kind") in FILE_EVIDENCE_KINDS:
            snapshot = _snapshot_for_evidence(evidence)
            path = Path(str(evidence.get("uri") or ""))
            if not path.exists():
                if snapshot is None:
                    return {
                        "status": "missing_evidence",
                        "evidence_id": evidence_id,
                        "evidence": evidence,
                        "snapshot": None,
                        "navigation": None,
                    }
                return {
                    "status": "source_missing",
                    "evidence_id": evidence_id,
                    "evidence": evidence,
                    "snapshot": snapshot,
                    "navigation": None,
                }
            current_hash = hash_file(path)
            expected_hash = str(evidence.get("hash") or "")
            evidence = {**evidence, "current_hash": current_hash}
            status = "source_changed" if expected_hash and current_hash != expected_hash else "fresh"
        else:
            snapshot = _snapshot_for_evidence(evidence)

        return {
            "status": status,
            "evidence_id": evidence_id,
            "evidence": evidence,
            "snapshot": snapshot,
            "navigation": _navigation_for_evidence(evidence),
        }


def _snapshot_for_evidence(evidence: dict[str, Any]) -> dict[str, str] | None:
    snapshot_uri = str(evidence.get("snapshot_uri") or "").strip()
    if not snapshot_uri:
        return None
    path = Path(snapshot_uri)
    if not path.exists():
        return None
    return {
        "uri": str(path),
        "hash": hash_file(path),
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
