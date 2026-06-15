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


def _placeholders(values: list[str]) -> str:
    return ",".join("?" for _ in values)


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

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        columns = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
                    expires_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    label TEXT NOT NULL,
                    uri TEXT NOT NULL,
                    snapshot_uri TEXT NOT NULL DEFAULT '',
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

                CREATE TABLE IF NOT EXISTS run_events (
                    event_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    action_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
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

                CREATE TABLE IF NOT EXISTS work_orders (
                    work_order_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    desk TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    impact TEXT NOT NULL,
                    affected_files TEXT NOT NULL,
                    suggested_verification TEXT NOT NULL,
                    evidence_refs TEXT NOT NULL,
                    status TEXT NOT NULL,
                    resolution TEXT NOT NULL DEFAULT '',
                    resolved_at TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS programs (
                    program_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    desk TEXT NOT NULL,
                    status TEXT NOT NULL,
                    planning_mode TEXT NOT NULL,
                    max_steps INTEGER NOT NULL,
                    current_step INTEGER NOT NULL,
                    phases TEXT NOT NULL,
                    blocked_items TEXT NOT NULL,
                    boundary TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            self._ensure_column(conn, "actions", "expires_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "evidence", "snapshot_uri", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "work_orders", "resolution", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "work_orders", "resolved_at", "TEXT")

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

    def update_session(self, row: dict[str, Any]) -> None:
        payload = {**row, "tags": _json_dumps(row.get("tags", []))}
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET title = :title, status = :status, default_desk = :default_desk,
                    tags = :tags, updated_at = :updated_at
                WHERE session_id = :session_id
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
            "expires_at": row.get("expires_at", ""),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO actions(
                    action_id, session_id, desk, action_type, risk_level, status, summary, parameters,
                    expected_effect, evidence_refs, approval_required, approval_decision, expires_at, created_at, updated_at
                )
                VALUES(
                    :action_id, :session_id, :desk, :action_type, :risk_level, :status, :summary, :parameters,
                    :expected_effect, :evidence_refs, :approval_required, :approval_decision, :expires_at, :created_at, :updated_at
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
        payload = {**row, "snapshot_uri": row.get("snapshot_uri", "")}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO evidence(evidence_id, kind, label, uri, snapshot_uri, summary, generated_at, hash, freshness_status)
                VALUES(:evidence_id, :kind, :label, :uri, :snapshot_uri, :summary, :generated_at, :hash, :freshness_status)
                """,
                payload,
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

    def insert_run_event(self, row: dict[str, Any]) -> None:
        payload = {**row, "payload": _json_dumps(row.get("payload", {}))}
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO run_events(
                    event_id, run_id, action_id, sequence, event_type, status, message, payload, created_at
                )
                VALUES(
                    :event_id, :run_id, :action_id, :sequence, :event_type, :status, :message, :payload, :created_at
                )
                """,
                payload,
            )

    def next_run_event_sequence(self, run_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM run_events WHERE run_id = ?", (run_id,)).fetchone()
        return int(row[0])

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

    def insert_work_order(self, row: dict[str, Any]) -> None:
        payload = {
            **row,
            "affected_files": _json_dumps(row.get("affected_files", [])),
            "suggested_verification": _json_dumps(row.get("suggested_verification", [])),
            "evidence_refs": _json_dumps(row.get("evidence_refs", [])),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO work_orders(
                    work_order_id, session_id, desk, title, summary, impact, affected_files,
                    suggested_verification, evidence_refs, status, resolution, resolved_at,
                    created_by, created_at, updated_at
                )
                VALUES(
                    :work_order_id, :session_id, :desk, :title, :summary, :impact, :affected_files,
                    :suggested_verification, :evidence_refs, :status, :resolution, :resolved_at,
                    :created_by, :created_at, :updated_at
                )
                """,
                payload,
            )

    def insert_program(self, row: dict[str, Any]) -> None:
        payload = {
            **row,
            "phases": _json_dumps(row.get("phases", [])),
            "blocked_items": _json_dumps(row.get("blocked_items", [])),
            "boundary": _json_dumps(row.get("boundary", {})),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO programs(
                    program_id, session_id, goal, desk, status, planning_mode, max_steps,
                    current_step, phases, blocked_items, boundary, created_at, updated_at
                )
                VALUES(
                    :program_id, :session_id, :goal, :desk, :status, :planning_mode, :max_steps,
                    :current_step, :phases, :blocked_items, :boundary, :created_at, :updated_at
                )
                """,
                payload,
            )

    def update_program(self, row: dict[str, Any]) -> None:
        payload = {
            **row,
            "phases": _json_dumps(row.get("phases", [])),
            "blocked_items": _json_dumps(row.get("blocked_items", [])),
            "boundary": _json_dumps(row.get("boundary", {})),
        }
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE programs
                SET status = :status, current_step = :current_step, phases = :phases,
                    blocked_items = :blocked_items, boundary = :boundary, updated_at = :updated_at
                WHERE program_id = :program_id
                """,
                payload,
            )

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC, session_id DESC").fetchall()
        return [self._session_row(row) for row in rows]

    def list_session_ids_by_status(self, status: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT session_id FROM sessions WHERE status = ? ORDER BY created_at ASC", (status,)).fetchall()
        return [str(row["session_id"]) for row in rows]

    def memory_counts(self) -> dict[str, int]:
        with self._connect() as conn:
            return {
                "sessions": int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]),
                "messages": int(conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]),
                "actions": int(conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]),
                "runs": int(conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]),
                "run_events": int(conn.execute("SELECT COUNT(*) FROM run_events").fetchone()[0]),
                "evidence": int(conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]),
                "handoffs": int(conn.execute("SELECT COUNT(*) FROM handoffs").fetchone()[0]),
                "work_orders": int(conn.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]),
                "programs": int(conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0]),
            }

    def delete_sessions(self, session_ids: list[str], *, dry_run: bool = False) -> dict[str, int]:
        ids = [str(session_id) for session_id in session_ids if str(session_id)]
        if not ids:
            return {"sessions": 0, "messages": 0, "actions": 0, "runs": 0, "run_events": 0, "evidence": 0, "handoffs": 0, "work_orders": 0, "programs": 0}
        placeholders = _placeholders(ids)
        with self._connect() as conn:
            action_rows = conn.execute(
                f"SELECT action_id FROM actions WHERE session_id IN ({placeholders})",
                ids,
            ).fetchall()
            action_ids = [str(row["action_id"]) for row in action_rows]
            action_placeholders = _placeholders(action_ids)
            run_ids = [
                str(row["run_id"])
                for row in (
                    conn.execute(
                        f"SELECT run_id FROM runs WHERE action_id IN ({action_placeholders})",
                        action_ids,
                    ).fetchall()
                    if action_ids
                    else []
                )
            ]
            candidate_evidence = self._session_evidence_refs(conn, ids, action_ids)
            outside_evidence = self._outside_session_evidence_refs(conn, ids, action_ids)
            evidence_to_delete = sorted(candidate_evidence - outside_evidence)
            counts = {
                "sessions": int(conn.execute(f"SELECT COUNT(*) FROM sessions WHERE session_id IN ({placeholders})", ids).fetchone()[0]),
                "messages": int(conn.execute(f"SELECT COUNT(*) FROM messages WHERE session_id IN ({placeholders})", ids).fetchone()[0]),
                "actions": len(action_ids),
                "runs": int(
                    len(run_ids)
                ),
                "run_events": int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM run_events WHERE action_id IN ({action_placeholders})",
                        action_ids,
                    ).fetchone()[0]
                    if action_ids
                    else 0
                ),
                "evidence": len(evidence_to_delete),
                "handoffs": int(conn.execute(f"SELECT COUNT(*) FROM handoffs WHERE session_id IN ({placeholders})", ids).fetchone()[0]),
                "work_orders": int(conn.execute(f"SELECT COUNT(*) FROM work_orders WHERE session_id IN ({placeholders})", ids).fetchone()[0]),
                "programs": int(conn.execute(f"SELECT COUNT(*) FROM programs WHERE session_id IN ({placeholders})", ids).fetchone()[0]),
            }
            if dry_run:
                return counts
            if action_ids:
                conn.execute(f"DELETE FROM run_events WHERE action_id IN ({action_placeholders})", action_ids)
                conn.execute(f"DELETE FROM runs WHERE action_id IN ({action_placeholders})", action_ids)
                conn.execute(f"DELETE FROM actions WHERE action_id IN ({action_placeholders})", action_ids)
            conn.execute(f"DELETE FROM handoffs WHERE session_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM work_orders WHERE session_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM programs WHERE session_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM messages WHERE session_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM sessions WHERE session_id IN ({placeholders})", ids)
            if evidence_to_delete:
                evidence_placeholders = _placeholders(evidence_to_delete)
                conn.execute(f"DELETE FROM evidence WHERE evidence_id IN ({evidence_placeholders})", evidence_to_delete)
            return counts

    def clear_memory(self, *, dry_run: bool = False) -> dict[str, int]:
        counts = self.memory_counts()
        if dry_run:
            return counts
        with self._connect() as conn:
            for table in ("run_events", "runs", "handoffs", "work_orders", "programs", "actions", "messages", "evidence", "sessions"):
                conn.execute(f"DELETE FROM {table}")
        return counts

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        return self._session_row(row) if row else None

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC, rowid ASC",
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

    def list_evidence(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM evidence ORDER BY generated_at DESC, evidence_id DESC").fetchall()
        return [dict(row) for row in rows]

    def list_runs(self, action_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if action_id:
                rows = conn.execute(
                    "SELECT * FROM runs WHERE action_id = ? ORDER BY started_at DESC, rowid DESC",
                    (action_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM runs ORDER BY started_at DESC, rowid DESC").fetchall()
        return [self._run_row(row) for row in rows]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._run_row(row) if row else None

    def list_run_events(self, run_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if run_id:
                rows = conn.execute(
                    "SELECT * FROM run_events WHERE run_id = ? ORDER BY sequence ASC, rowid ASC",
                    (run_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM run_events ORDER BY created_at ASC, rowid ASC").fetchall()
        return [self._run_event_row(row) for row in rows]

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

    def get_handoff(self, handoff_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM handoffs WHERE handoff_id = ?", (handoff_id,)).fetchone()
        return self._handoff_row(row) if row else None

    def update_handoff_status(self, handoff_id: str, status: str, resolved_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE handoffs
                SET status = ?, resolved_at = ?
                WHERE handoff_id = ?
                """,
                (status, resolved_at, handoff_id),
            )

    def list_work_orders(self, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM work_orders WHERE session_id = ? ORDER BY created_at DESC, work_order_id DESC",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM work_orders ORDER BY created_at DESC, work_order_id DESC").fetchall()
        return [self._work_order_row(row) for row in rows]

    def get_work_order(self, work_order_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM work_orders WHERE work_order_id = ?", (work_order_id,)).fetchone()
        return self._work_order_row(row) if row else None

    def list_programs(self, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM programs WHERE session_id = ? ORDER BY created_at DESC, program_id DESC",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM programs ORDER BY created_at DESC, program_id DESC").fetchall()
        return [self._program_row(row) for row in rows]

    def get_program(self, program_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM programs WHERE program_id = ?", (program_id,)).fetchone()
        return self._program_row(row) if row else None

    def update_work_order_status(
        self,
        work_order_id: str,
        *,
        status: str,
        resolution: str,
        resolved_at: str | None,
        updated_at: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE work_orders
                SET status = ?, resolution = ?, resolved_at = ?, updated_at = ?
                WHERE work_order_id = ?
                """,
                (status, resolution, resolved_at, updated_at, work_order_id),
            )

    @staticmethod
    def _collect_json_refs(rows: list[sqlite3.Row], column: str) -> set[str]:
        refs: set[str] = set()
        for row in rows:
            refs.update(str(value) for value in _json_loads(row[column], []) if str(value))
        return refs

    def _session_evidence_refs(self, conn: sqlite3.Connection, session_ids: list[str], action_ids: list[str]) -> set[str]:
        placeholders = _placeholders(session_ids)
        refs = self._collect_json_refs(
            conn.execute(f"SELECT evidence_refs FROM messages WHERE session_id IN ({placeholders})", session_ids).fetchall(),
            "evidence_refs",
        )
        refs.update(
            self._collect_json_refs(
                conn.execute(f"SELECT evidence_refs FROM actions WHERE session_id IN ({placeholders})", session_ids).fetchall(),
                "evidence_refs",
            )
        )
        refs.update(
            self._collect_json_refs(
                conn.execute(f"SELECT evidence_refs FROM handoffs WHERE session_id IN ({placeholders})", session_ids).fetchall(),
                "evidence_refs",
            )
        )
        refs.update(
            self._collect_json_refs(
                conn.execute(f"SELECT evidence_refs FROM work_orders WHERE session_id IN ({placeholders})", session_ids).fetchall(),
                "evidence_refs",
            )
        )
        if action_ids:
            action_placeholders = _placeholders(action_ids)
            refs.update(
                self._collect_json_refs(
                    conn.execute(f"SELECT artifact_refs FROM runs WHERE action_id IN ({action_placeholders})", action_ids).fetchall(),
                    "artifact_refs",
                )
            )
        return refs

    def _outside_session_evidence_refs(self, conn: sqlite3.Connection, session_ids: list[str], action_ids: list[str]) -> set[str]:
        placeholders = _placeholders(session_ids)
        refs = self._collect_json_refs(
            conn.execute(f"SELECT evidence_refs FROM messages WHERE session_id NOT IN ({placeholders})", session_ids).fetchall(),
            "evidence_refs",
        )
        refs.update(
            self._collect_json_refs(
                conn.execute(f"SELECT evidence_refs FROM actions WHERE session_id NOT IN ({placeholders})", session_ids).fetchall(),
                "evidence_refs",
            )
        )
        refs.update(
            self._collect_json_refs(
                conn.execute(f"SELECT evidence_refs FROM handoffs WHERE session_id NOT IN ({placeholders})", session_ids).fetchall(),
                "evidence_refs",
            )
        )
        refs.update(
            self._collect_json_refs(
                conn.execute(f"SELECT evidence_refs FROM work_orders WHERE session_id NOT IN ({placeholders})", session_ids).fetchall(),
                "evidence_refs",
            )
        )
        if action_ids:
            action_placeholders = _placeholders(action_ids)
            refs.update(
                self._collect_json_refs(
                    conn.execute(f"SELECT artifact_refs FROM runs WHERE action_id NOT IN ({action_placeholders})", action_ids).fetchall(),
                    "artifact_refs",
                )
            )
        else:
            refs.update(self._collect_json_refs(conn.execute("SELECT artifact_refs FROM runs").fetchall(), "artifact_refs"))
        return refs

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
    def _run_event_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["payload"] = _json_loads(data.get("payload"), {})
        return data

    @staticmethod
    def _handoff_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["evidence_refs"] = _json_loads(data.get("evidence_refs"), [])
        return data

    @staticmethod
    def _work_order_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["affected_files"] = _json_loads(data.get("affected_files"), [])
        data["suggested_verification"] = _json_loads(data.get("suggested_verification"), [])
        data["evidence_refs"] = _json_loads(data.get("evidence_refs"), [])
        return data

    @staticmethod
    def _program_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["phases"] = _json_loads(data.get("phases"), [])
        data["blocked_items"] = _json_loads(data.get("blocked_items"), [])
        data["boundary"] = _json_loads(data.get("boundary"), {})
        data["max_steps"] = int(data.get("max_steps") or 0)
        data["current_step"] = int(data.get("current_step") or 0)
        data["phase_count"] = len(data["phases"])
        data["safe_action_count"] = sum(1 for phase in data["phases"] if str(phase.get("status") or "") != "blocked")
        data["blocked_item_count"] = len(data["blocked_items"])
        return data
