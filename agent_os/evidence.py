from __future__ import annotations

import hashlib
import shlex
from pathlib import Path
from typing import Any
from urllib.parse import quote

from agent_os.ledger import AgentLedger


FILE_EVIDENCE_KINDS = {"artifact", "file", "code", "report", "ledger"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_EVIDENCE_PATH_PARTS = {".git", ".venv", "node_modules"}


def hash_file(path: str | Path) -> str:
    safe_path = safe_existing_file_path(path)
    if safe_path is None:
        raise ValueError("Unsafe evidence file path")
    digest = hashlib.sha256()
    with safe_path.open("rb") as f:
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
            path = safe_file_evidence_path(str(evidence.get("uri") or ""))
            if path is None:
                return {
                    "status": "unsafe_evidence_uri",
                    "evidence_id": evidence_id,
                    "evidence": evidence,
                    "snapshot": snapshot,
                    "navigation": None,
                }
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
    path = safe_existing_file_path(snapshot_uri)
    if path is None:
        return None
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
    if kind == "api_endpoint":
        return _api_navigation_for_evidence(evidence)
    if kind == "cli_command":
        return _cli_navigation_for_evidence(evidence)
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


def safe_file_evidence_path(uri: str) -> Path | None:
    path_text, _line = split_file_evidence_uri(uri)
    return safe_existing_file_path(path_text)


def safe_existing_file_path(path_text: str | Path) -> Path | None:
    path_text = str(path_text or "").strip()
    if not path_text:
        return None
    if "://" in path_text:
        return None
    path = Path(path_text)
    resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    if not _is_allowed_file_evidence_path(resolved):
        return None
    return resolved


def _is_allowed_file_evidence_path(path: Path) -> bool:
    for root in _allowed_file_evidence_roots():
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if any(part in FORBIDDEN_EVIDENCE_PATH_PARTS for part in relative.parts):
            return False
        return True
    return False


def _allowed_file_evidence_roots() -> tuple[Path, ...]:
    roots = [PROJECT_ROOT.resolve()]
    try:
        from data.storage.datahub import get_datahub

        roots.append(get_datahub().runtime_dir().resolve())
    except Exception:
        pass
    return tuple(dict.fromkeys(roots))


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


def _api_navigation_for_evidence(evidence: dict[str, Any]) -> dict[str, str] | None:
    uri = str(evidence.get("uri") or "").strip()
    if not uri.startswith("/api/") or not _is_safe_local_route(uri):
        return None
    return {
        "kind": "api_endpoint",
        "method": "GET",
        "href": uri,
        "label": str(evidence.get("label") or uri),
    }


def _cli_navigation_for_evidence(evidence: dict[str, Any]) -> dict[str, Any] | None:
    command = str(evidence.get("uri") or "").strip()
    if not command or _has_shell_syntax(command):
        return None
    try:
        argv = shlex.split(command)
    except ValueError:
        return None
    if not argv or Path(argv[0]).name != "astroq":
        return None
    if argv[0] not in {"astroq", ".venv/bin/astroq"}:
        return None
    return {
        "kind": "cli_command",
        "command": " ".join(argv),
        "argv": argv,
        "label": str(evidence.get("label") or command),
    }


def _has_shell_syntax(command: str) -> bool:
    shell_tokens = {";", "&&", "||", "|", "`", "$", ">", "<", "\n", "\r"}
    return any(token in command for token in shell_tokens)


def _safe_project_relative_path(path_text: str) -> str | None:
    if not path_text:
        return None
    path = Path(path_text)
    resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    try:
        relative = resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return None
    if any(part in FORBIDDEN_EVIDENCE_PATH_PARTS for part in relative.parts):
        return None
    return relative.as_posix()
