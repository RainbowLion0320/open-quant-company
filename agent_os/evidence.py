from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from urllib.parse import quote

from agent_os.ledger import AgentLedger


FILE_EVIDENCE_KINDS = {"artifact", "file", "code", "report", "ledger"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
            path = evidence_source_path(str(evidence.get("uri") or ""))
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
    if kind == "web_route":
        if not _is_safe_local_route(uri):
            return None
        return {
            "kind": "web_route",
            "href": uri,
            "label": str(evidence.get("label") or uri),
        }
    if kind in FILE_EVIDENCE_KINDS:
        return _file_navigation_for_evidence(evidence)
    return None


def _is_safe_local_route(uri: str) -> bool:
    if not uri.startswith("/"):
        return False
    if uri.startswith("//"):
        return False
    return "\\" not in uri


def evidence_source_path(uri: str) -> Path:
    path_text, _line = split_file_evidence_uri(uri)
    path = Path(path_text)
    return path if path.is_absolute() else PROJECT_ROOT / path


def split_file_evidence_uri(uri: str) -> tuple[str, str | None]:
    clean_uri = str(uri or "").strip()
    if "://" in clean_uri:
        return clean_uri, None
    head, sep, tail = clean_uri.rpartition(":")
    if sep and head and tail.isdigit():
        return head, tail
    return clean_uri, None


def _file_navigation_for_evidence(evidence: dict[str, Any]) -> dict[str, str] | None:
    kind = str(evidence.get("kind") or "")
    uri = str(evidence.get("uri") or "").strip()
    path_text, line = split_file_evidence_uri(uri)
    safe_path = _safe_project_relative_path(path_text)
    if safe_path is None:
        return None
    nav_kind = "code" if kind == "code" else kind
    href = f"/system?tab=codegraph&file={quote(safe_path, safe='')}"
    result = {
        "kind": nav_kind,
        "path": safe_path,
        "href": href,
        "label": str(evidence.get("label") or safe_path),
    }
    if kind == "code" and line:
        result["line"] = line
        result["href"] = f"{href}&line={line}"
    return result


def _safe_project_relative_path(path_text: str) -> str | None:
    if not path_text:
        return None
    path = Path(path_text)
    resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    try:
        relative = resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    if any(part in {".git", ".venv", "node_modules"} for part in relative.parts):
        return None
    return relative.as_posix()
