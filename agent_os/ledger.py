from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from data.storage.datahub import get_datahub


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


class AgentLedger:
    """SQLite ledger for local Agent Company OS state."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path is not None else get_datahub().db_path("agent_os.sqlite")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    default_desk TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    desk TEXT NOT NULL,
                    content TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL,
                    action_refs TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS actions (
                    action_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    desk TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    status TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    expected_effect TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL,
                    approval_required INTEGER NOT NULL,
                    approval_decision TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    hash TEXT NOT NULL,
                    freshness_status TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    command TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    return_code INTEGER,
                    stdout_summary TEXT NOT NULL,
                    stderr_summary TEXT NOT NULL,
                    artifact_refs TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS handoffs (
                    handoff_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    source_message_id TEXT NOT NULL,
                    source_desk TEXT NOT NULL,
                    target_desk TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT NOT NULL
                );
                """
            )

    def insert_session(self, row: dict[str, Any]) -> None:
        payload = {**row, "tags": _json_dumps(row.get("tags", []))}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(session_id, title, status, created_by, default_desk, tags, created_at, updated_at)
                VALUES(:session_id, :title, :status, :created_by, :default_desk, :tags, :created_at, :updated_at)
                """,
                payload,
            )

    def insert_message(self, row: dict[str, Any]) -> None:
        payload = {
            **row,
            "evidence_refs": _json_dumps(row.get("evidence_refs", [])),
            "action_refs": _json_dumps(row.get("action_refs", [])),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages(message_id, session_id, role, desk, content, evidence_refs, action_refs, created_at)
                VALUES(:message_id, :session_id, :role, :desk, :content, :evidence_refs, :action_refs, :created_at)
                """,
                payload,
            )

    def insert_action(self, row: dict[str, Any]) -> None:
        payload = {
            **row,
            "parameters": _json_dumps(row.get("parameters", {})),
            "evidence_refs": _json_dumps(row.get("evidence_refs", [])),
            "approval_required": 1 if row.get("approval_required") else 0,
            "approval_decision": _json_dumps(row.get("approval_decision")) if row.get("approval_decision") else None,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO actions(
                    action_id, session_id, desk, action_type, risk_level, status, summary, parameters,
                    expected_effect, evidence_refs, approval_required, approval_decision, created_at, updated_at
                )
                VALUES(
                    :action_id, :session_id, :desk, :action_type, :risk_level, :status, :summary, :parameters,
                    :expected_effect, :evidence_refs, :approval_required, :approval_decision, :created_at, :updated_at
                )
                """,
                payload,
            )

    def update_action_decision(self, action_id: str, status: str, decision: dict[str, Any], updated_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE actions
                SET status = ?, approval_decision = ?, updated_at = ?
                WHERE action_id = ?
                """,
                (status, _json_dumps(decision), updated_at, action_id),
            )

    def update_action_status(self, action_id: str, status: str, updated_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE actions
                SET status = ?, updated_at = ?
                WHERE action_id = ?
                """,
                (status, updated_at, action_id),
            )

    def insert_evidence(self, row: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evidence(evidence_id, kind, label, uri, summary, generated_at, hash, freshness_status)
                VALUES(:evidence_id, :kind, :label, :uri, :summary, :generated_at, :hash, :freshness_status)
                """,
                row,
            )

    def insert_run(self, row: dict[str, Any]) -> None:
        payload = {
            **row,
            "command": _json_dumps(row.get("command", [])),
            "artifact_refs": _json_dumps(row.get("artifact_refs", [])),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs(
                    run_id, action_id, tool_name, command, started_at, finished_at, status, return_code,
                    stdout_summary, stderr_summary, artifact_refs
                )
                VALUES(
                    :run_id, :action_id, :tool_name, :command, :started_at, :finished_at, :status, :return_code,
                    :stdout_summary, :stderr_summary, :artifact_refs
                )
                """,
                payload,
            )

    def insert_handoff(self, row: dict[str, Any]) -> None:
        payload = {**row, "evidence_refs": _json_dumps(row.get("evidence_refs", []))}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO handoffs(
                    handoff_id, session_id, source_message_id, source_desk, target_desk,
                    reason, status, evidence_refs, created_at, resolved_at
                )
                VALUES(
                    :handoff_id, :session_id, :source_message_id, :source_desk, :target_desk,
                    :reason, :status, :evidence_refs, :created_at, :resolved_at
                )
                """,
                payload,
            )

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC, session_id DESC").fetchall()
        return [self._session_row(row) for row in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return self._session_row(row) if row else None

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC, message_id ASC",
                (session_id,),
            ).fetchall()
        return [self._message_row(row) for row in rows]

    def list_actions(self, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM actions WHERE session_id = ? ORDER BY created_at DESC, action_id DESC",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM actions ORDER BY created_at DESC, action_id DESC").fetchall()
        return [self._action_row(row) for row in rows]

    def get_action(self, action_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,)).fetchone()
        return self._action_row(row) if row else None

    def get_evidence(self, evidence_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
        return dict(row) if row else None

    def list_runs(self, action_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if action_id:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE action_id = ? ORDER BY started_at DESC, run_id DESC",
                    (action_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC, run_id DESC").fetchall()
        return [self._run_row(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._run_row(row) if row else None

    def list_handoffs(self, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM handoffs WHERE session_id = ? ORDER BY created_at DESC, handoff_id DESC",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM handoffs ORDER BY created_at DESC, handoff_id DESC").fetchall()
        return [self._handoff_row(row) for row in rows]

    @staticmethod
    def _session_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["tags"] = _json_loads(data.get("tags"), [])
        return data

    @staticmethod
    def _message_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["evidence_refs"] = _json_loads(data.get("evidence_refs"), [])
        data["action_refs"] = _json_loads(data.get("action_refs"), [])
        return data

    @staticmethod
    def _action_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["parameters"] = _json_loads(data.get("parameters"), {})
        data["evidence_refs"] = _json_loads(data.get("evidence_refs"), [])
        data["approval_required"] = bool(data.get("approval_required"))
        data["approval_decision"] = _json_loads(data.get("approval_decision"), None)
        return data

    @staticmethod
    def _run_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["command"] = _json_loads(data.get("command"), [])
        data["artifact_refs"] = _json_loads(data.get("artifact_refs"), [])
        return data

    @staticmethod
    def _handoff_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["evidence_refs"] = _json_loads(data.get("evidence_refs"), [])
        return data
