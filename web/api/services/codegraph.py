"""Read-only CodeGraph index service for the Web UI."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

VISUAL_EDGE_KINDS = ("imports", "calls", "instantiates", "references", "extends")
SYMBOL_NODE_KINDS = ("class", "function", "method", "component", "route", "interface", "type_alias")
_SYNC_LOCK = threading.Lock()


@dataclass
class CodeGraphCommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


class CodeGraphService:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.db_path = self.project_root / ".codegraph" / "codegraph.db"

    def status(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {
                "initialized": False,
                "file_count": 0,
                "node_count": 0,
                "edge_count": 0,
                "db_size_bytes": 0,
                "backend": "",
                "languages": [],
                "nodes_by_kind": {},
                "pending_changes": {"added": 0, "modified": 0, "removed": 0},
                "stale": True,
                "message": "CodeGraph index is not initialized.",
            }

        cli_status = self._cli_status()
        with self._connect() as con:
            row = con.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM files) AS file_count,
                    (SELECT COUNT(*) FROM nodes) AS node_count,
                    (SELECT COUNT(*) FROM edges) AS edge_count
                """
            ).fetchone()
            languages = [
                {"language": item["language"], "files": item["files"], "nodes": item["nodes"] or 0}
                for item in con.execute(
                    "SELECT language, COUNT(*) AS files, SUM(node_count) AS nodes FROM files GROUP BY language ORDER BY nodes DESC"
                ).fetchall()
            ]
            nodes_by_kind = {
                item["kind"]: item["count"]
                for item in con.execute("SELECT kind, COUNT(*) AS count FROM nodes GROUP BY kind ORDER BY count DESC").fetchall()
            }

        pending = (cli_status or {}).get("pendingChanges") or {"added": 0, "modified": 0, "removed": 0}
        stale = any(int(pending.get(key, 0) or 0) > 0 for key in ("added", "modified", "removed"))
        return {
            "initialized": True,
            "file_count": int(row["file_count"]),
            "node_count": int(row["node_count"]),
            "edge_count": int(row["edge_count"]),
            "db_size_bytes": self.db_path.stat().st_size,
            "backend": (cli_status or {}).get("backend", "sqlite"),
            "languages": languages,
            "nodes_by_kind": nodes_by_kind,
            "pending_changes": pending,
            "stale": stale,
            "message": "" if not stale else "CodeGraph index has pending worktree changes.",
        }

    def graph(
        self,
        *,
        level: str = "module",
        root: str = "",
        edge_kinds: Iterable[str] | None = None,
        node_kinds: Iterable[str] | None = None,
        limit: int = 300,
    ) -> dict[str, Any]:
        edge_filter = _clean_filter(edge_kinds, VISUAL_EDGE_KINDS)
        node_filter = _clean_filter(node_kinds, SYMBOL_NODE_KINDS)
        bounded_limit = _bounded_limit(limit)
        if level == "module":
            return self._module_graph(edge_filter, bounded_limit)
        if level == "file":
            return self._file_graph(root, edge_filter, bounded_limit)
        if level == "symbol":
            return self._symbol_graph(root, edge_filter, node_filter, bounded_limit)
        raise ValueError(f"Unsupported CodeGraph level: {level}")

    def search(self, q: str, limit: int = 20) -> list[dict[str, Any]]:
        query = q.strip()
        if not query or not self.db_path.exists():
            return []
        bounded_limit = _bounded_limit(limit, default=20, maximum=50)
        pattern = f"%{query.lower()}%"
        with self._connect() as con:
            rows = con.execute(
                """
                SELECT id, kind, name, qualified_name, file_path, language, start_line, end_line, docstring, signature
                FROM nodes
                WHERE lower(name) LIKE ? OR lower(qualified_name) LIKE ? OR lower(file_path) LIKE ?
                ORDER BY
                    CASE WHEN lower(name) = lower(?) THEN 0 ELSE 1 END,
                    CASE kind
                        WHEN 'class' THEN 0
                        WHEN 'function' THEN 1
                        WHEN 'method' THEN 2
                        WHEN 'component' THEN 3
                        WHEN 'route' THEN 4
                        WHEN 'file' THEN 5
                        ELSE 6
                    END,
                    length(qualified_name)
                LIMIT ?
                """,
                (pattern, pattern, pattern, query, bounded_limit),
            ).fetchall()
        return [self._node_payload(row) for row in rows]

    def neighborhood(self, node_id: str, depth: int = 1, limit: int = 180) -> dict[str, Any]:
        if not node_id or not self.db_path.exists():
            return self._empty_graph(level="neighborhood")
        bounded_limit = _bounded_limit(limit, default=180, maximum=500)
        max_depth = max(1, min(int(depth or 1), 3))
        nodes: dict[str, dict[str, Any]] = {}
        links: dict[tuple[str, str, str], dict[str, Any]] = {}
        frontier = {node_id}
        visited = {node_id}

        with self._connect() as con:
            seed = con.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
            if not seed:
                return self._empty_graph(level="neighborhood")
            nodes[node_id] = self._node_payload(seed)
            for _ in range(max_depth):
                if len(nodes) >= bounded_limit or not frontier:
                    break
                placeholders = ",".join("?" for _ in frontier)
                rows = con.execute(
                    f"""
                    SELECT
                        e.kind AS edge_kind,
                        e.source,
                        e.target,
                        s.id AS source_id, s.kind AS source_kind, s.name AS source_name,
                        s.qualified_name AS source_qualified_name, s.file_path AS source_file_path,
                        s.language AS source_language, s.start_line AS source_start_line,
                        s.end_line AS source_end_line, s.docstring AS source_docstring,
                        s.signature AS source_signature,
                        t.id AS target_id, t.kind AS target_kind, t.name AS target_name,
                        t.qualified_name AS target_qualified_name, t.file_path AS target_file_path,
                        t.language AS target_language, t.start_line AS target_start_line,
                        t.end_line AS target_end_line, t.docstring AS target_docstring,
                        t.signature AS target_signature
                    FROM edges e
                    JOIN nodes s ON s.id = e.source
                    JOIN nodes t ON t.id = e.target
                    WHERE e.kind IN ({','.join('?' for _ in VISUAL_EDGE_KINDS)})
                      AND (e.source IN ({placeholders}) OR e.target IN ({placeholders}))
                    LIMIT ?
                    """,
                    (*VISUAL_EDGE_KINDS, *frontier, *frontier, bounded_limit * 4),
                ).fetchall()
                next_frontier: set[str] = set()
                for row in rows:
                    source = _node_from_prefixed_row(row, "source")
                    target = _node_from_prefixed_row(row, "target")
                    for item in (source, target):
                        if len(nodes) < bounded_limit:
                            nodes.setdefault(item["id"], item)
                    key = (row["source"], row["target"], row["edge_kind"])
                    links[key] = _link_payload(row["source"], row["target"], row["edge_kind"], row["edge_kind"], 1)
                    for item_id in (row["source"], row["target"]):
                        if item_id not in visited:
                            next_frontier.add(item_id)
                            visited.add(item_id)
                frontier = next_frontier

        return self._graph_payload("neighborhood", list(nodes.values()), list(links.values()), len(nodes) >= bounded_limit)

    def _module_graph(self, edge_filter: tuple[str, ...], limit: int) -> dict[str, Any]:
        if not self.db_path.exists():
            return self._empty_graph(level="module")
        nodes: dict[str, dict[str, Any]] = {}
        links: dict[tuple[str, str, str], dict[str, Any]] = {}
        with self._connect() as con:
            for row in con.execute("SELECT path, language, node_count FROM files").fetchall():
                top = _top_module(row["path"])
                node_id = f"module:{top}"
                node = nodes.setdefault(
                    node_id,
                    {
                        "id": node_id,
                        "label": top,
                        "kind": "module",
                        "path": top,
                        "qualified_name": top,
                        "language": "mixed",
                        "start_line": None,
                        "end_line": None,
                        "count": 0,
                        "degree": 0,
                        "group": top,
                    },
                )
                node["count"] += int(row["node_count"] or 0)
            for row in self._edge_file_rows(con, edge_filter):
                source = f"module:{_top_module(row['source_file_path'])}"
                target = f"module:{_top_module(row['target_file_path'])}"
                if source == target or source not in nodes or target not in nodes:
                    continue
                _add_counted_link(links, source, target, row["edge_kind"])
                nodes[source]["degree"] += 1
                nodes[target]["degree"] += 1

        return self._limited_graph("module", nodes, links, limit)

    def _file_graph(self, root: str, edge_filter: tuple[str, ...], limit: int) -> dict[str, Any]:
        if not self.db_path.exists():
            return self._empty_graph(level="file")
        root_prefix = _normalize_root(root)
        nodes: dict[str, dict[str, Any]] = {}
        links: dict[tuple[str, str, str], dict[str, Any]] = {}
        file_degree: dict[str, int] = {}

        with self._connect() as con:
            files = con.execute("SELECT path, language, node_count FROM files").fetchall()
            internal_paths = {row["path"] for row in files if _path_in_root(row["path"], root_prefix)}
            for row in files:
                if row["path"] not in internal_paths:
                    continue
                node_id = f"file:{row['path']}"
                nodes[node_id] = _file_node(row["path"], row["language"], int(row["node_count"] or 0), root_prefix)

            for row in self._edge_file_rows(con, edge_filter):
                src_path = row["source_file_path"]
                tgt_path = row["target_file_path"]
                src_internal = src_path in internal_paths
                tgt_internal = tgt_path in internal_paths
                if not src_internal and not tgt_internal:
                    continue
                source_id = f"file:{src_path}" if src_internal else f"external:{_top_module(src_path)}"
                target_id = f"file:{tgt_path}" if tgt_internal else f"external:{_top_module(tgt_path)}"
                if source_id == target_id:
                    continue
                if not src_internal:
                    nodes.setdefault(source_id, _external_node(_top_module(src_path)))
                if not tgt_internal:
                    nodes.setdefault(target_id, _external_node(_top_module(tgt_path)))
                _add_counted_link(links, source_id, target_id, row["edge_kind"])
                file_degree[source_id] = file_degree.get(source_id, 0) + 1
                file_degree[target_id] = file_degree.get(target_id, 0) + 1

        for node_id, degree in file_degree.items():
            if node_id in nodes:
                nodes[node_id]["degree"] = degree
        return self._limited_graph("file", nodes, links, limit)

    def _symbol_graph(
        self,
        root: str,
        edge_filter: tuple[str, ...],
        node_filter: tuple[str, ...],
        limit: int,
    ) -> dict[str, Any]:
        if not self.db_path.exists() or not root:
            return self._empty_graph(level="symbol")
        root_path = _normalize_file_root(root)
        nodes: dict[str, dict[str, Any]] = {}
        links: dict[tuple[str, str, str], dict[str, Any]] = {}
        with self._connect() as con:
            file_row = con.execute("SELECT path, language, node_count FROM files WHERE path = ?", (root_path,)).fetchone()
            if not file_row:
                return self._empty_graph(level="symbol")
            file_id = f"file:{root_path}"
            nodes[file_id] = _file_node(root_path, file_row["language"], int(file_row["node_count"] or 0), _top_module(root_path))
            placeholders = ",".join("?" for _ in node_filter)
            symbol_rows = con.execute(
                f"SELECT * FROM nodes WHERE file_path = ? AND kind IN ({placeholders}) ORDER BY start_line",
                (root_path, *node_filter),
            ).fetchall()
            symbol_ids = {row["id"] for row in symbol_rows}
            for row in symbol_rows:
                nodes[row["id"]] = self._node_payload(row)

            if symbol_ids:
                edge_placeholders = ",".join("?" for _ in (*edge_filter, "contains"))
                id_placeholders = ",".join("?" for _ in symbol_ids)
                edge_rows = con.execute(
                    f"""
                    SELECT e.kind AS edge_kind, e.source, e.target,
                           s.id AS source_id, s.kind AS source_kind, s.name AS source_name,
                           s.qualified_name AS source_qualified_name, s.file_path AS source_file_path,
                           s.language AS source_language, s.start_line AS source_start_line,
                           s.end_line AS source_end_line, s.docstring AS source_docstring,
                           s.signature AS source_signature,
                           t.id AS target_id, t.kind AS target_kind, t.name AS target_name,
                           t.qualified_name AS target_qualified_name, t.file_path AS target_file_path,
                           t.language AS target_language, t.start_line AS target_start_line,
                           t.end_line AS target_end_line, t.docstring AS target_docstring,
                           t.signature AS target_signature
                    FROM edges e
                    JOIN nodes s ON s.id = e.source
                    JOIN nodes t ON t.id = e.target
                    WHERE e.kind IN ({edge_placeholders})
                      AND (e.source = ? OR e.source IN ({id_placeholders}) OR e.target IN ({id_placeholders}))
                    LIMIT ?
                    """,
                    (*edge_filter, "contains", file_id, *symbol_ids, *symbol_ids, limit * 3),
                ).fetchall()
                for row in edge_rows:
                    for item in (_node_from_prefixed_row(row, "source"), _node_from_prefixed_row(row, "target")):
                        if item["id"] == file_id or item["id"] in symbol_ids or len(nodes) < limit:
                            nodes.setdefault(item["id"], item)
                    if row["source"] in nodes and row["target"] in nodes:
                        _add_counted_link(links, row["source"], row["target"], row["edge_kind"])
                        nodes[row["source"]]["degree"] = nodes[row["source"]].get("degree", 0) + 1
                        nodes[row["target"]]["degree"] = nodes[row["target"]].get("degree", 0) + 1

        return self._limited_graph("symbol", nodes, links, limit)

    def _edge_file_rows(self, con: sqlite3.Connection, edge_filter: tuple[str, ...]) -> list[sqlite3.Row]:
        placeholders = ",".join("?" for _ in edge_filter)
        return con.execute(
            f"""
            SELECT e.kind AS edge_kind, s.file_path AS source_file_path, t.file_path AS target_file_path
            FROM edges e
            JOIN nodes s ON s.id = e.source
            JOIN nodes t ON t.id = e.target
            WHERE e.kind IN ({placeholders})
            """,
            edge_filter,
        ).fetchall()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con

    def _cli_status(self) -> dict[str, Any] | None:
        try:
            result = subprocess.run(
                ["codegraph", "status", str(self.project_root), "--json"],
                cwd=self.project_root,
                text=True,
                capture_output=True,
                timeout=20,
                check=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return None

    def _node_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        degree = self._node_degree(row["id"])
        return {
            "id": row["id"],
            "label": row["name"],
            "kind": row["kind"],
            "path": row["file_path"],
            "qualified_name": row["qualified_name"],
            "language": row["language"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "count": 1,
            "degree": degree,
            "group": _top_module(row["file_path"]),
            "signature": row["signature"],
            "docstring": row["docstring"],
        }

    def _node_degree(self, node_id: str) -> int:
        with self._connect() as con:
            row = con.execute("SELECT COUNT(*) AS count FROM edges WHERE source = ? OR target = ?", (node_id, node_id)).fetchone()
            return int(row["count"] or 0)

    def _limited_graph(
        self,
        level: str,
        nodes: dict[str, dict[str, Any]],
        links: dict[tuple[str, str, str], dict[str, Any]],
        limit: int,
    ) -> dict[str, Any]:
        ordered_nodes = sorted(nodes.values(), key=lambda item: (item.get("degree", 0), item.get("count", 0)), reverse=True)
        truncated = len(ordered_nodes) > limit
        kept = ordered_nodes[:limit]
        kept_ids = {node["id"] for node in kept}
        kept_links = [link for link in links.values() if link["source"] in kept_ids and link["target"] in kept_ids]
        return self._graph_payload(level, kept, kept_links, truncated)

    def _graph_payload(
        self,
        level: str,
        nodes: list[dict[str, Any]],
        links: list[dict[str, Any]],
        truncated: bool,
    ) -> dict[str, Any]:
        return {
            "level": level,
            "nodes": nodes,
            "links": links,
            "stats": {**self.status(), "truncated": truncated},
        }

    def _empty_graph(self, level: str) -> dict[str, Any]:
        return {"level": level, "nodes": [], "links": [], "stats": {**self.status(), "truncated": False}}


def run_codegraph_sync(project_root: Path, mode: str) -> dict[str, Any]:
    root = project_root.resolve()
    if mode not in {"sync", "rebuild"}:
        return {"status": "failed", "message": f"Unsupported sync mode: {mode}"}
    if not _SYNC_LOCK.acquire(blocking=False):
        return {"status": "conflict", "message": "CodeGraph sync is already running."}
    try:
        commands = [["codegraph", "sync", str(root)]]
        if mode == "rebuild":
            commands = [
                ["codegraph", "uninit", "--force", str(root)],
                ["codegraph", "init", str(root)],
                ["codegraph", "index", str(root)],
            ]
        results = []
        for args in commands:
            result = subprocess.run(
                args,
                cwd=root,
                text=True,
                capture_output=True,
                timeout=180,
                check=False,
            )
            results.append({
                "args": list(result.args),
                "returncode": int(result.returncode),
                "stdout": result.stdout,
                "stderr": result.stderr,
            })
            if result.returncode != 0:
                return {"status": "failed", "mode": mode, "results": results, "message": result.stderr or result.stdout}
        return {"status": "ok", "mode": mode, "results": results}
    finally:
        _SYNC_LOCK.release()


def _clean_filter(values: Iterable[str] | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not values:
        return default
    allowed = set(default)
    cleaned = tuple(item for item in values if item in allowed)
    return cleaned or default


def _bounded_limit(limit: int, default: int = 300, maximum: int = 800) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def _top_module(path: str) -> str:
    return (path or "root").split("/", 1)[0] or "root"


def _normalize_root(root: str) -> str:
    value = (root or "").strip().strip("/")
    return value or ""


def _normalize_file_root(root: str) -> str:
    return _normalize_root(root).removeprefix("file:")


def _path_in_root(path: str, root: str) -> bool:
    return not root or path == root or path.startswith(f"{root}/")


def _file_node(path: str, language: str, count: int, group: str) -> dict[str, Any]:
    return {
        "id": f"file:{path}",
        "label": Path(path).name,
        "kind": "file",
        "path": path,
        "qualified_name": path,
        "language": language,
        "start_line": 1,
        "end_line": None,
        "count": count,
        "degree": 0,
        "group": group,
    }


def _external_node(module: str) -> dict[str, Any]:
    return {
        "id": f"external:{module}",
        "label": module,
        "kind": "external_module",
        "path": module,
        "qualified_name": module,
        "language": "mixed",
        "start_line": None,
        "end_line": None,
        "count": 0,
        "degree": 0,
        "group": module,
    }


def _node_from_prefixed_row(row: sqlite3.Row, prefix: str) -> dict[str, Any]:
    return {
        "id": row[f"{prefix}_id"],
        "label": row[f"{prefix}_name"],
        "kind": row[f"{prefix}_kind"],
        "path": row[f"{prefix}_file_path"],
        "qualified_name": row[f"{prefix}_qualified_name"],
        "language": row[f"{prefix}_language"],
        "start_line": row[f"{prefix}_start_line"],
        "end_line": row[f"{prefix}_end_line"],
        "count": 1,
        "degree": 0,
        "group": _top_module(row[f"{prefix}_file_path"]),
        "signature": row[f"{prefix}_signature"],
        "docstring": row[f"{prefix}_docstring"],
    }


def _add_counted_link(links: dict[tuple[str, str, str], dict[str, Any]], source: str, target: str, edge_kind: str) -> None:
    key = (source, target, edge_kind)
    if key not in links:
        links[key] = _link_payload(source, target, edge_kind, edge_kind, 0)
    links[key]["count"] += 1
    links[key]["label"] = f"{edge_kind} ×{links[key]['count']}"


def _link_payload(source: str, target: str, edge_kind: str, label: str, count: int) -> dict[str, Any]:
    return {
        "source": source,
        "target": target,
        "type": edge_kind,
        "label": label,
        "count": count,
        "direction": "outbound",
    }
