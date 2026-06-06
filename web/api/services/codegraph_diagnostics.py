"""Deterministic architecture diagnostics for the CodeGraph index."""

from __future__ import annotations

import sqlite3
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VISUAL_EDGE_KINDS = ("imports", "calls", "instantiates", "references", "extends")
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}


@dataclass
class FileMetrics:
    path: str
    language: str
    node_count: int
    line_count: int = 0
    incoming: int = 0
    outgoing: int = 0
    internal: int = 0
    inbound_files: set[str] = field(default_factory=set)
    outbound_files: set[str] = field(default_factory=set)
    inbound_modules: set[str] = field(default_factory=set)
    outbound_modules: set[str] = field(default_factory=set)

    @property
    def degree(self) -> int:
        return self.incoming + self.outgoing + self.internal


class CodeGraphDiagnosticsService:
    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.db_path = self.project_root / ".codegraph" / "codegraph.db"

    def diagnostics(
        self,
        *,
        scope: str = "summary",
        root: str = "",
        limit: int = 80,
        include_git: bool = True,
    ) -> dict[str, Any]:
        bounded_limit = _bounded_limit(limit)
        normalized_root = _normalize_root(root)
        if not self.db_path.exists():
            return _empty_payload(initialized=False, limit=bounded_limit)

        git_head = self._git_head() if include_git else ""
        cache_key = (
            str(self.db_path),
            self.db_path.stat().st_mtime_ns,
            git_head,
            scope,
            normalized_root,
            bounded_limit,
            include_git,
        )
        if cache_key in _CACHE:
            return _CACHE[cache_key]

        churn = self._git_churn() if include_git else None
        git_churn_available = churn is not None
        churn = churn or {}

        with self._connect() as con:
            metrics = self._load_file_metrics(con)
            edges = self._load_edges(con)

        self._apply_edge_metrics(metrics, edges)
        issues = []
        edge_flags = []
        issues.extend(self._cycle_issues(metrics, edges))
        cross_layer, flags = self._cross_layer_issues(edges)
        issues.extend(cross_layer)
        edge_flags.extend(flags)
        issues.extend(self._hotspot_issues(metrics, churn, git_churn_available))
        issues.extend(self._orphan_issues(metrics))
        issues.extend(self._internal_api_leak_issues(metrics))
        issues.extend(self._large_connected_file_issues(metrics))

        filtered = [issue for issue in issues if _issue_in_scope(issue, scope, normalized_root)]
        ordered = sorted(filtered, key=_issue_sort_key)
        truncated = len(ordered) > bounded_limit
        limited = ordered[:bounded_limit]
        node_scores = _node_scores(limited)
        payload = {
            "summary": {
                "initialized": True,
                "issue_count": len(limited),
                "total_issue_count": len(filtered),
                "severity_counts": dict(Counter(issue["severity"] for issue in limited)),
                "risk_score": _risk_score(limited),
                "git_churn_available": git_churn_available,
                "stale": False,
                "truncated": truncated,
            },
            "issues": limited,
            "node_scores": node_scores,
            "edge_flags": [flag for flag in edge_flags if _edge_flag_in_scope(flag, scope, normalized_root)][:bounded_limit],
        }
        _CACHE[cache_key] = payload
        if len(_CACHE) > 16:
            _CACHE.pop(next(iter(_CACHE)))
        return payload

    def _load_file_metrics(self, con: sqlite3.Connection) -> dict[str, FileMetrics]:
        metrics = {
            row["path"]: FileMetrics(
                path=row["path"],
                language=row["language"],
                node_count=int(row["node_count"] or 0),
            )
            for row in con.execute("SELECT path, language, node_count FROM files").fetchall()
        }
        for row in con.execute("SELECT file_path, MAX(end_line) AS line_count FROM nodes GROUP BY file_path").fetchall():
            if row["file_path"] in metrics:
                metrics[row["file_path"]].line_count = int(row["line_count"] or 0)
        return metrics

    def _load_edges(self, con: sqlite3.Connection) -> list[dict[str, Any]]:
        placeholders = ",".join("?" for _ in VISUAL_EDGE_KINDS)
        rows = con.execute(
            f"""
            SELECT
                e.kind,
                e.source,
                e.target,
                s.file_path AS source_path,
                t.file_path AS target_path
            FROM edges e
            JOIN nodes s ON s.id = e.source
            JOIN nodes t ON t.id = e.target
            WHERE e.kind IN ({placeholders})
            """,
            VISUAL_EDGE_KINDS,
        ).fetchall()
        return [dict(row) for row in rows]

    def _apply_edge_metrics(self, metrics: dict[str, FileMetrics], edges: list[dict[str, Any]]) -> None:
        for edge in edges:
            source = edge["source_path"]
            target = edge["target_path"]
            if source not in metrics or target not in metrics:
                continue
            source_metric = metrics[source]
            target_metric = metrics[target]
            if source == target:
                source_metric.internal += 1
                continue
            source_metric.outgoing += 1
            target_metric.incoming += 1
            source_metric.outbound_files.add(target)
            target_metric.inbound_files.add(source)
            source_metric.outbound_modules.add(_top_module(target))
            target_metric.inbound_modules.add(_top_module(source))

    def _cycle_issues(self, metrics: dict[str, FileMetrics], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
        graph: dict[str, set[str]] = defaultdict(set)
        for edge in edges:
            if edge["kind"] not in {"imports", "extends"}:
                continue
            source = edge["source_path"]
            target = edge["target_path"]
            if source in metrics and target in metrics and source != target:
                graph[source].add(target)
        issues = []
        for component in _strongly_connected_components(graph):
            if len(component) < 2:
                continue
            paths = sorted(component)
            severity = "P0" if len(paths) >= 3 else "P1"
            issues.append(_issue(
                category="cycle",
                severity=severity,
                title="File dependency cycle",
                path=paths[0],
                node_id=f"file:{paths[0]}",
                source=paths[0],
                target=paths[1],
                evidence={"files": paths, "size": len(paths)},
                recommendation="Break the cycle by moving the shared contract behind a lower-level facade.",
            ))
        return issues

    def _cross_layer_issues(self, edges: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        issues = []
        flags = []
        seen: set[tuple[str, str, str]] = set()
        for edge in edges:
            source = edge["source_path"]
            target = edge["target_path"]
            if source == target:
                continue
            rule = _cross_layer_rule(source, target, edge["kind"])
            if not rule:
                continue
            key = (source, target, rule)
            if key in seen:
                continue
            seen.add(key)
            issues.append(_issue(
                category="cross_layer",
                severity="P0",
                title="Cross-layer dependency",
                path=source,
                node_id=f"file:{source}",
                source=source,
                target=target,
                evidence={"rule": rule, "edge_kind": edge["kind"]},
                recommendation="Route the dependency through the intended service/facade boundary.",
            ))
            flags.append({"source": f"file:{source}", "target": f"file:{target}", "category": "cross_layer", "severity": "P0"})
        return issues, flags

    def _hotspot_issues(
        self,
        metrics: dict[str, FileMetrics],
        churn: dict[str, int],
        git_churn_available: bool,
    ) -> list[dict[str, Any]]:
        issues = []
        for metric in metrics.values():
            churn_count = int(churn.get(metric.path, 0))
            high_degree = metric.degree >= 20 or metric.incoming >= 15 or metric.outgoing >= 15
            churn_hotspot = git_churn_available and metric.degree >= 4 and churn_count >= 5
            if not high_degree and not churn_hotspot:
                continue
            severity = "P0" if metric.degree >= 80 or churn_count >= 15 else "P1" if metric.degree >= 30 or churn_count >= 10 else "P2"
            issues.append(_issue(
                category="hotspot",
                severity=severity,
                title="High-coupling hotspot",
                path=metric.path,
                node_id=f"file:{metric.path}",
                evidence={
                    "degree": metric.degree,
                    "incoming": metric.incoming,
                    "outgoing": metric.outgoing,
                    "git_churn_90d": churn_count if git_churn_available else None,
                },
                recommendation="Inspect whether this file should be split behind a narrower public interface.",
            ))
        return issues

    def _orphan_issues(self, metrics: dict[str, FileMetrics]) -> list[dict[str, Any]]:
        issues = []
        for metric in metrics.values():
            if metric.incoming or metric.outgoing or metric.internal:
                continue
            if not _is_production_candidate(metric.path) or _is_entry_like(metric.path):
                continue
            issues.append(_issue(
                category="orphan",
                severity="P2",
                title="Orphan production file candidate",
                path=metric.path,
                node_id=f"file:{metric.path}",
                evidence={"incoming": 0, "outgoing": 0},
                recommendation="Confirm whether this file is a dynamic entrypoint; otherwise remove it or wire it through the canonical path.",
            ))
        return issues

    def _internal_api_leak_issues(self, metrics: dict[str, FileMetrics]) -> list[dict[str, Any]]:
        issues = []
        for metric in metrics.values():
            if not _is_internal_path(metric.path):
                continue
            if len(metric.inbound_modules) < 2 or metric.incoming < 2:
                continue
            issues.append(_issue(
                category="internal_api_leak",
                severity="P1",
                title="Internal API leak",
                path=metric.path,
                node_id=f"file:{metric.path}",
                evidence={"incoming": metric.incoming, "inbound_modules": sorted(metric.inbound_modules)},
                recommendation="Expose a stable facade and move external callers off the internal file.",
            ))
        return issues

    def _large_connected_file_issues(self, metrics: dict[str, FileMetrics]) -> list[dict[str, Any]]:
        issues = []
        for metric in metrics.values():
            large = metric.line_count >= 700 or metric.node_count >= 20
            if not large or metric.degree < 2:
                continue
            severity = "P1" if metric.degree >= 6 or metric.line_count >= 900 else "P2"
            issues.append(_issue(
                category="large_connected_file",
                severity=severity,
                title="Large connected file",
                path=metric.path,
                node_id=f"file:{metric.path}",
                evidence={"line_count": metric.line_count, "node_count": metric.node_count, "degree": metric.degree},
                recommendation="Split independent responsibilities before adding new behavior to this file.",
            ))
        return issues

    def _git_head(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_root,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except Exception:
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    def _git_churn(self) -> dict[str, int] | None:
        try:
            result = subprocess.run(
                ["git", "log", "--since=90.days", "--name-only", "--format="],
                cwd=self.project_root,
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
        except Exception:
            return None
        if result.returncode != 0:
            return None
        counts: Counter[str] = Counter()
        for line in result.stdout.splitlines():
            path = line.strip()
            if path:
                counts[path] += 1
        return dict(counts)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        return con


def _empty_payload(*, initialized: bool, limit: int) -> dict[str, Any]:
    return {
        "summary": {
            "initialized": initialized,
            "issue_count": 0,
            "total_issue_count": 0,
            "severity_counts": {},
            "risk_score": 0,
            "git_churn_available": False,
            "stale": not initialized,
            "truncated": False,
        },
        "issues": [],
        "node_scores": {},
        "edge_flags": [],
    }


def _issue(
    *,
    category: str,
    severity: str,
    title: str,
    path: str,
    node_id: str,
    evidence: dict[str, Any],
    recommendation: str,
    source: str = "",
    target: str = "",
) -> dict[str, Any]:
    stable = f"{category}:{path}:{source}:{target}:{title}".replace(" ", "-")
    return {
        "id": stable,
        "severity": severity,
        "category": category,
        "title": title,
        "node_id": node_id,
        "source": source,
        "target": target,
        "path": path,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def _strongly_connected_components(graph: dict[str, set[str]]) -> list[set[str]]:
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indexes: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    components: list[set[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, set()):
            if target not in indexes:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indexes[target])
        if lowlinks[node] != indexes[node]:
            return
        component = set()
        while stack:
            item = stack.pop()
            on_stack.remove(item)
            component.add(item)
            if item == node:
                break
        components.append(component)

    for node in sorted(set(graph) | {target for targets in graph.values() for target in targets}):
        if node not in indexes:
            visit(node)
    return components


def _cross_layer_rule(source: str, target: str, edge_kind: str) -> str:
    stable_structural_edge = edge_kind in {"imports", "references", "instantiates", "extends"}
    if not stable_structural_edge:
        return ""
    if source.startswith("web/api/routes/") and target.startswith("data/"):
        return "web_api_route_direct_to_data"
    if source.startswith("data/") and target.startswith("web/"):
        return "data_depends_on_web"
    upper_roots = ("web/", "pipeline/", "backtest/", "models/", "research/", "signals/", "broker/", "cybernetics/")
    if source.startswith("data/storage/") and target.startswith(upper_roots):
        return "storage_depends_on_upper_layer"
    return ""


def _node_scores(issues: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    scores: dict[str, dict[str, Any]] = {}
    weights = {"P0": 45, "P1": 25, "P2": 10}
    for issue in issues:
        node_id = issue["node_id"]
        item = scores.setdefault(node_id, {"score": 0, "severity": "P2", "categories": []})
        item["score"] = min(100, item["score"] + weights[issue["severity"]])
        if SEVERITY_ORDER[issue["severity"]] < SEVERITY_ORDER[item["severity"]]:
            item["severity"] = issue["severity"]
        if issue["category"] not in item["categories"]:
            item["categories"].append(issue["category"])
    return scores


def _risk_score(issues: list[dict[str, Any]]) -> int:
    if not issues:
        return 0
    weights = {"P0": 30, "P1": 15, "P2": 5}
    return min(100, sum(weights[issue["severity"]] for issue in issues))


def _issue_sort_key(issue: dict[str, Any]) -> tuple[int, str, str]:
    return (SEVERITY_ORDER.get(issue["severity"], 9), issue["category"], issue["path"])


def _issue_in_scope(issue: dict[str, Any], scope: str, root: str) -> bool:
    if not root or scope == "summary":
        return True
    paths = [issue.get("path", ""), issue.get("source", ""), issue.get("target", "")]
    return any(path == root or path.startswith(f"{root}/") for path in paths if path)


def _edge_flag_in_scope(flag: dict[str, Any], scope: str, root: str) -> bool:
    if not root or scope == "summary":
        return True
    source = flag.get("source", "").removeprefix("file:")
    target = flag.get("target", "").removeprefix("file:")
    return source.startswith(root) or target.startswith(root)


def _bounded_limit(limit: int, default: int = 80, maximum: int = 200) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def _normalize_root(root: str) -> str:
    return (root or "").strip().strip("/").removeprefix("file:")


def _top_module(path: str) -> str:
    return (path or "root").split("/", 1)[0] or "root"


def _is_production_candidate(path: str) -> bool:
    excluded = ("tests/", "docs/", "wiki/", "var/", ".codegraph/")
    return not path.startswith(excluded)


def _is_entry_like(path: str) -> bool:
    name = Path(path).name
    return path.startswith("scripts/") or name in {"__init__.py", "main.py", "app.py"}


def _is_internal_path(path: str) -> bool:
    name = Path(path).name
    return "/internal" in path or name.startswith("_")
