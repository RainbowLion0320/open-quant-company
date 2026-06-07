from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

from data.storage.datahub import get_datahub

RECOMMENDED_AST_COMMAND = "astroq architecture ast --json"
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".vue", ".css"}
FRONTEND_SUFFIXES = {".ts", ".tsx", ".js", ".mjs", ".vue", ".css"}
EXCLUDED_ROOTS = {
    ".codegraph",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "docs",
    "node_modules",
    "var",
    "web/frontend/dist",
    "web/frontend/node_modules",
    "web/frontend/tmp",
    "wiki",
}
MIN_CLONE_NODES = 8
NEAR_CLONE_THRESHOLD = 0.88


@dataclass(frozen=True)
class UnitRef:
    id: str
    path: str
    language: str
    kind: str
    name: str
    start_line: int
    end_line: int
    node_count: int
    fingerprint: str
    tokens: tuple[str, ...]
    calls: tuple[str, ...] = ()
    imports: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()

    @property
    def module(self) -> str:
        return self.path.split("/", 1)[0] if "/" in self.path else self.path


def collect_ast_intelligence(project_root: Path) -> dict[str, Any]:
    project_root = Path(project_root).resolve()
    files = _discover_files(project_root)
    python_files = [path for path in files if path.suffix == ".py"]
    frontend_files = [path for path in files if path.suffix in FRONTEND_SUFFIXES]

    units: list[UnitRef] = []
    errors: list[dict[str, Any]] = []
    py_units, py_errors = _collect_python_units(project_root, python_files)
    units.extend(py_units)
    errors.extend(py_errors)
    if frontend_files:
        frontend_units, frontend_errors = _collect_frontend_units(project_root, frontend_files)
        units.extend(frontend_units)
        errors.extend(frontend_errors)

    clone_groups = _clone_groups(units)
    issues = _issues_from_clone_groups(clone_groups)
    issues.extend(_canonical_bypass_issues(project_root, files, units))
    graph = _graph_payload(units, clone_groups)
    summary = _summary_payload(files, units, issues, clone_groups)
    status = "ok" if files else "empty"
    if errors and not units:
        status = "error"
    return {
        "status": status,
        "generated_at": _utc_now(),
        "recommended_command": RECOMMENDED_AST_COMMAND,
        "summary": summary,
        "issues": issues,
        "clone_groups": clone_groups,
        "graph": graph,
        "errors": errors[:50],
    }


def write_ast_intelligence_artifact(payload: dict[str, Any]) -> Path:
    artifact_dir = get_datahub().artifact_dir("architecture") / "ast"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "latest.json"
    get_datahub().write_json(payload, path, indent=2)
    return path


def _discover_files(project_root: Path) -> list[Path]:
    tracked = _git_tracked(project_root)
    if tracked:
        candidates = [project_root / item for item in tracked]
    else:
        candidates = [path for path in project_root.rglob("*") if path.is_file()]
    files = []
    for path in candidates:
        if path.suffix not in SOURCE_SUFFIXES or not path.exists():
            continue
        rel = path.relative_to(project_root).as_posix()
        if _excluded(rel):
            continue
        files.append(path)
    return sorted(set(files), key=lambda item: item.relative_to(project_root).as_posix())


def _git_tracked(project_root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _excluded(rel: str) -> bool:
    parts = rel.split("/")
    for root in EXCLUDED_ROOTS:
        root_parts = root.split("/")
        if parts[: len(root_parts)] == root_parts:
            return True
    return False


def _collect_python_units(project_root: Path, files: list[Path]) -> tuple[list[UnitRef], list[dict[str, Any]]]:
    units: list[UnitRef] = []
    errors: list[dict[str, Any]] = []
    for path in files:
        rel = path.relative_to(project_root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            errors.append({"path": rel, "language": "python", "message": str(exc), "line": exc.lineno or 0})
            continue
        imports = tuple(sorted(_python_imports(tree)))
        for node in _python_unit_nodes(tree):
            tokens = tuple(_python_tokens(node))
            if not tokens:
                continue
            name = getattr(node, "name", "<unit>")
            unit_id = f"unit:{rel}:{int(getattr(node, 'lineno', 0) or 0)}:{name}"
            units.append(
                UnitRef(
                    id=unit_id,
                    path=rel,
                    language="python",
                    kind=_python_kind(node),
                    name=name,
                    start_line=int(getattr(node, "lineno", 0) or 0),
                    end_line=int(getattr(node, "end_lineno", getattr(node, "lineno", 0)) or 0),
                    node_count=len(tokens),
                    fingerprint=_fingerprint(tokens),
                    tokens=tokens,
                    calls=tuple(sorted(_python_calls(node))),
                    imports=imports,
                )
            )
    return units, errors


def _python_unit_nodes(tree: ast.AST) -> list[ast.AST]:
    items: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            items.append(node)
    return sorted(items, key=lambda node: (int(getattr(node, "lineno", 0) or 0), getattr(node, "name", "")))


def _python_kind(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        return "class"
    if isinstance(node, ast.AsyncFunctionDef):
        return "async-function"
    return "function"


def _python_tokens(node: ast.AST) -> list[str]:
    tokens: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, (ast.Load, ast.Store, ast.Del, ast.Param)):
            continue
        if isinstance(child, ast.Name):
            tokens.append("Name")
        elif isinstance(child, ast.arg):
            tokens.append("Arg")
        elif isinstance(child, ast.Attribute):
            tokens.append("Attribute")
        elif isinstance(child, ast.Constant):
            tokens.append(f"Constant:{type(child.value).__name__}")
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            tokens.append(type(child).__name__)
        else:
            tokens.append(type(child).__name__)
    return tokens


def _python_calls(node: ast.AST) -> set[str]:
    calls: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            name = _python_full_name(child.func)
            if name:
                calls.add(name)
    return calls


def _python_imports(tree: ast.AST) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _python_full_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _python_full_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _collect_frontend_units(project_root: Path, files: list[Path]) -> tuple[list[UnitRef], list[dict[str, Any]]]:
    helper = Path(__file__).resolve().parents[1] / "scripts" / "ast_frontend_collector.mjs"
    if not helper.exists():
        raise RuntimeError(f"Missing frontend AST helper: {helper}")
    payload = {
        "projectRoot": project_root.as_posix(),
        "files": [path.as_posix() for path in files],
    }
    result = subprocess.run(
        ["node", helper.as_posix()],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Frontend AST parser failed. Run npm install in web/frontend. {detail}")
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Frontend AST parser returned invalid JSON: {exc}") from exc
    units = [_unit_from_frontend(item) for item in data.get("units", []) or [] if isinstance(item, dict)]
    errors = [item for item in data.get("errors", []) or [] if isinstance(item, dict)]
    return units, errors


def _unit_from_frontend(item: dict[str, Any]) -> UnitRef:
    tokens = tuple(str(token) for token in item.get("tokens", []) or [])
    return UnitRef(
        id=str(item.get("id") or f"unit:{item.get('path')}:{item.get('start_line')}:{item.get('name')}"),
        path=str(item.get("path") or ""),
        language=str(item.get("language") or "unknown"),
        kind=str(item.get("kind") or "unit"),
        name=str(item.get("name") or "<unit>"),
        start_line=int(item.get("start_line") or 0),
        end_line=int(item.get("end_line") or item.get("start_line") or 0),
        node_count=int(item.get("node_count") or len(tokens)),
        fingerprint=str(item.get("fingerprint") or _fingerprint(tokens)),
        tokens=tokens,
        calls=tuple(sorted(str(value) for value in item.get("calls", []) or [])),
        imports=tuple(sorted(str(value) for value in item.get("imports", []) or [])),
        exports=tuple(sorted(str(value) for value in item.get("exports", []) or [])),
    )


def _clone_groups(units: list[UnitRef]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    seen_unit_pairs: set[tuple[str, str]] = set()
    by_fingerprint: dict[str, list[UnitRef]] = defaultdict(list)
    for unit in units:
        if _clone_candidate(unit):
            by_fingerprint[unit.fingerprint].append(unit)
    for fingerprint, items in sorted(by_fingerprint.items()):
        if len(items) < 2:
            continue
        category = "style_clone" if all(item.kind == "style-rule" for item in items) else "exact_clone"
        group = _group_payload(category, 1.0, items, fingerprint)
        groups.append(group)
        seen_unit_pairs.update(_unit_pairs(items))

    by_bucket: dict[tuple[str, str], list[UnitRef]] = defaultdict(list)
    for unit in units:
        if _clone_candidate(unit):
            by_bucket[(unit.language, unit.kind)].append(unit)
    near_index = 0
    for items in by_bucket.values():
        ordered = sorted(items, key=lambda item: item.id)
        for left, right in combinations(ordered, 2):
            pair = tuple(sorted((left.id, right.id)))
            if pair in seen_unit_pairs:
                continue
            if not _same_size_band(left, right):
                continue
            score = _jaccard(_shingles(left.tokens), _shingles(right.tokens))
            if score >= NEAR_CLONE_THRESHOLD:
                near_index += 1
                groups.append(_group_payload("near_clone", score, [left, right], f"near-{near_index}"))
                seen_unit_pairs.add(pair)

    groups.extend(_duplicate_helper_groups(units, seen_unit_pairs))
    return groups


def _clone_candidate(unit: UnitRef) -> bool:
    if unit.kind == "style-rule":
        return unit.node_count >= 3
    if unit.node_count < MIN_CLONE_NODES:
        return False
    if unit.kind in {"file", "import"}:
        return False
    if unit.kind in {"function", "async-function", "ts-function", "method"} and unit.node_count < 12 and len(unit.calls) <= 1:
        return False
    return True


def _same_size_band(left: UnitRef, right: UnitRef) -> bool:
    small = max(1, min(left.node_count, right.node_count))
    large = max(left.node_count, right.node_count)
    return large / small <= 1.35


def _duplicate_helper_groups(units: list[UnitRef], seen_pairs: set[tuple[str, str]]) -> list[dict[str, Any]]:
    groups = []
    buckets: dict[str, list[UnitRef]] = defaultdict(list)
    for unit in units:
        if not _clone_candidate(unit) or unit.kind not in {"function", "async-function", "ts-function", "method"}:
            continue
        key = _helper_key(unit.name)
        if key:
            buckets[key].append(unit)
    index = 0
    for key, items in sorted(buckets.items()):
        distinct_paths = {unit.path for unit in items}
        if len(items) < 2 or len(distinct_paths) < 2:
            continue
        fresh_pairs = [pair for pair in _unit_pairs(items) if pair not in seen_pairs]
        if not fresh_pairs:
            continue
        index += 1
        groups.append(_group_payload("duplicate_helper", 0.76, items[:8], f"helper-{key}-{index}"))
    return groups


def _helper_key(name: str) -> str:
    lowered = "".join(ch for ch in name.lower() if ch.isalpha() or ch == "_")
    for prefix in ("get_", "build_", "make_", "create_", "format_", "normalize_", "parse_", "safe_"):
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix):]
    lowered = lowered.strip("_")
    return lowered if len(lowered) >= 6 else ""


def _group_payload(category: str, similarity: float, units: list[UnitRef], shared_shape: str) -> dict[str, Any]:
    sorted_units = sorted(units, key=lambda item: (item.path, item.start_line, item.name))
    group_id = f"{category}:{hashlib.sha1('|'.join(unit.id for unit in sorted_units).encode()).hexdigest()[:12]}"
    return {
        "id": group_id,
        "category": category,
        "similarity": round(float(similarity), 4),
        "units": [_unit_payload(unit) for unit in sorted_units],
        "shared_shape": shared_shape,
        "module_pairs": _module_pairs(sorted_units),
    }


def _unit_payload(unit: UnitRef) -> dict[str, Any]:
    return {
        "id": unit.id,
        "path": unit.path,
        "language": unit.language,
        "kind": unit.kind,
        "name": unit.name,
        "start_line": unit.start_line,
        "end_line": unit.end_line,
        "node_count": unit.node_count,
    }


def _unit_pairs(units: list[UnitRef]) -> set[tuple[str, str]]:
    return {tuple(sorted((left.id, right.id))) for left, right in combinations(units, 2)}


def _module_pairs(units: list[UnitRef]) -> list[str]:
    pairs = {":".join(sorted((left.module, right.module))) for left, right in combinations(units, 2) if left.module != right.module}
    return sorted(pairs)


def _issues_from_clone_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    titles = {
        "exact_clone": "Exact AST clone",
        "near_clone": "Near AST clone",
        "duplicate_helper": "Duplicate helper candidate",
        "style_clone": "Duplicate style rule",
    }
    recommendations = {
        "exact_clone": "Extract the shared logic behind a canonical helper or delete the duplicate implementation.",
        "near_clone": "Review whether these units should share a common helper before adding new behavior.",
        "duplicate_helper": "Prefer one public helper with narrow inputs instead of parallel helper implementations.",
        "style_clone": "Move repeated declarations into a shared class, token, or component-local utility.",
    }
    for group in groups:
        category = group["category"]
        severity = _clone_severity(group)
        issue_id = f"{category}:{group['id']}"
        issues.append({
            "id": issue_id,
            "severity": severity,
            "category": category,
            "title": titles.get(category, category.replace("_", " ").title()),
            "paths": sorted({unit["path"] for unit in group["units"]}),
            "units": group["units"],
            "language": _dominant_language(group["units"]),
            "evidence": {
                "similarity": group["similarity"],
                "unit_count": len(group["units"]),
                "shared_shape": group["shared_shape"],
                "module_pairs": group["module_pairs"],
            },
            "recommendation": recommendations.get(category, "Review this AST duplication candidate."),
        })
    return issues


def _clone_severity(group: dict[str, Any]) -> str:
    paths = [unit["path"] for unit in group["units"]]
    if all(path.startswith("tests/") for path in paths):
        return "P2"
    category = group["category"]
    if category == "exact_clone" and len({unit["path"] for unit in group["units"]}) > 1:
        return "P1"
    return "P2"


def _dominant_language(units: list[dict[str, Any]]) -> str:
    counts = Counter(str(unit.get("language") or "unknown") for unit in units)
    return counts.most_common(1)[0][0] if counts else "unknown"


def _canonical_bypass_issues(project_root: Path, files: list[Path], units: list[UnitRef]) -> list[dict[str, Any]]:
    file_text: dict[str, str] = {}
    for path in files:
        rel = path.relative_to(project_root).as_posix()
        try:
            file_text[rel] = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            file_text[rel] = ""

    checks = [
        {
            "id": "canonical_bypass:datahub_snapshot_discovery",
            "paths": ["signals/multifactor.py", "web/api/services/sectors.py"],
            "tokens": ['glob("*.parquet")', "glob('*.parquet')"],
            "required": "latest_dimension_snapshot",
            "recommendation": "Use DataHub latest_dimension_snapshot instead of reimplementing snapshot discovery.",
        },
        {
            "id": "canonical_bypass:strategy_scoring_helpers",
            "paths": ["backtest/strategy_scorers.py"],
            "tokens": ["np.diff(", "np.std(", "bull_sectors =", "bear_sectors =", "sideways_sectors ="],
            "required": "technical_factors_from_series",
            "recommendation": "Reuse shared signal scoring helpers instead of local technical factor math.",
        },
        {
            "id": "canonical_bypass:regime_metric_helpers",
            "paths": ["research/regime/evaluation.py", "research/regime/features.py"],
            "tokens": ["def _portfolio_metrics(", "def _future_compound_return("],
            "required": "",
            "recommendation": "Reuse research.performance and research.forward_labels helpers.",
        },
        {
            "id": "canonical_bypass:shared_serializers",
            "paths": ["web/api/services/system_common.py"],
            "tokens": ["def safe_float(", "def safe_int(", "def json_value(", "def json_map("],
            "required": "",
            "recommendation": "Keep JSON serializer helpers in the canonical serializer module only.",
        },
    ]

    issues = []
    unit_by_path = defaultdict(list)
    for unit in units:
        unit_by_path[unit.path].append(_unit_payload(unit))
    for check in checks:
        offenders = []
        for rel in check["paths"]:
            text = file_text.get(rel, "")
            if not text:
                continue
            if any(token in text for token in check["tokens"]):
                required = check.get("required") or ""
                if required and required in text:
                    continue
                offenders.append(rel)
        if offenders:
            issues.append({
                "id": check["id"],
                "severity": "P1",
                "category": "canonical_bypass",
                "title": "Canonical helper bypass",
                "paths": offenders,
                "units": [unit for path in offenders for unit in unit_by_path.get(path, [])[:5]],
                "language": "python",
                "evidence": {"tokens": check["tokens"]},
                "recommendation": check["recommendation"],
            })
    return issues


def _graph_payload(units: list[UnitRef], groups: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    links: Counter[tuple[str, str, str]] = Counter()

    def add_node(node_id: str, label: str, kind: str, group: str, path: str = "", count: int = 1) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"id": node_id, "label": label, "kind": kind, "group": group, "path": path, "count": 0}
        nodes[node_id]["count"] += count

    def add_link(source: str, target: str, kind: str) -> None:
        links[(source, target, kind)] += 1

    for unit in units:
        module_id = f"module:{unit.module}"
        file_id = f"file:{unit.path}"
        add_node(module_id, unit.module, "module", unit.module, unit.module)
        add_node(file_id, unit.path.rsplit("/", 1)[-1], "file", unit.module, unit.path)
        add_node(unit.id, unit.name, unit.kind, unit.module, unit.path)
        add_link(module_id, file_id, "contains")
        add_link(file_id, unit.id, "contains")
    for group in groups:
        group_id = f"clone:{group['id']}"
        add_node(group_id, group["category"], "clone_group", group["category"], "", len(group["units"]))
        for unit in group["units"]:
            add_link(group_id, unit["id"], "duplicates" if group["category"] in {"exact_clone", "style_clone"} else "similar_to")
    return {
        "nodes": sorted(nodes.values(), key=lambda item: (item["kind"], item["id"])),
        "links": [
            {"source": source, "target": target, "type": kind, "label": kind, "count": count}
            for (source, target, kind), count in sorted(links.items())
        ],
    }


def _summary_payload(
    files: list[Path],
    units: list[UnitRef],
    issues: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    severity_counts = Counter(issue["severity"] for issue in issues)
    language_counts = Counter(unit.language for unit in units)
    weights = {"P0": 30, "P1": 15, "P2": 5}
    duplicate_score = min(100, sum(weights.get(issue["severity"], 3) for issue in issues))
    return {
        "file_count": len(files),
        "unit_count": len(units),
        "issue_count": len(issues),
        "clone_group_count": len(groups),
        "languages": dict(sorted(language_counts.items())),
        "severity_counts": dict(severity_counts),
        "duplicate_score": duplicate_score,
        "truncated": False,
    }


def _fingerprint(tokens: tuple[str, ...] | list[str]) -> str:
    return hashlib.sha1("\n".join(tokens).encode("utf-8")).hexdigest()


def _shingles(tokens: tuple[str, ...], size: int = 4) -> set[tuple[str, ...]]:
    if len(tokens) < size:
        return {tokens} if tokens else set()
    return {tokens[index:index + size] for index in range(len(tokens) - size + 1)}


def _jaccard(left: set[Any], right: set[Any]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
