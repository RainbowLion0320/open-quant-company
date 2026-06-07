from __future__ import annotations

import ast
import fnmatch
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.storage.datahub import get_datahub

RECOMMENDED_DESIGN_COMMAND = "astroq test design --json"
TEST_KINDS = ("unit", "contract", "integration", "architecture", "api", "e2e")
PRODUCTION_ROOTS = {
    "astrolabe_cli",
    "backtest",
    "broker",
    "core",
    "cybernetics",
    "data",
    "models",
    "pipeline",
    "research",
    "scripts",
    "signals",
    "web",
}
STD_MODULES = {
    "argparse",
    "collections",
    "datetime",
    "functools",
    "itertools",
    "json",
    "math",
    "os",
    "pathlib",
    "re",
    "sqlite3",
    "subprocess",
    "sys",
    "tempfile",
    "textwrap",
    "time",
    "typing",
    "unittest",
    "uuid",
}


def collect_test_design(project_root: Path, config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = config or {}
    project_root = Path(project_root)
    files = _discover_files(project_root, config)
    cases: list[dict[str, Any]] = []
    file_counts: Counter[str] = Counter()

    for path in files:
        rel = path.relative_to(project_root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            cases.append(_syntax_error_case(rel, exc))
            continue
        module_imports = sorted(_target_modules_from_imports(tree, top_level_only=True))
        for item in _iter_test_functions(tree, rel):
            case = _case_payload(item, rel, module_imports, config)
            cases.append(case)
            file_counts[rel] += 1

    smells = _diagnose_design(cases, file_counts, config)
    matrix = _matrix_payload(cases, config)
    graph = _graph_payload(cases, smells)
    summary = _summary_payload(cases, smells, matrix, files)
    return {
        "status": "ok" if cases else "empty",
        "generated_at": _utc_now(),
        "recommended_command": RECOMMENDED_DESIGN_COMMAND,
        "summary": summary,
        "matrix": matrix,
        "graph": graph,
        "cases": cases,
        "smells": smells,
    }


def write_test_design_artifact(payload: dict[str, Any]) -> Path:
    artifact_dir = get_datahub().artifact_dir("tests") / "design"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "latest.json"
    get_datahub().write_json(payload, path, indent=2)
    return path


def _discover_files(project_root: Path, config: dict[str, Any]) -> list[Path]:
    globs = config.get("design", {}).get("scan_globs", ["tests/test*.py"])
    files: set[Path] = set()
    for pattern in globs:
        files.update(path for path in project_root.glob(str(pattern)) if path.is_file() and "__pycache__" not in path.parts)
    return sorted(files)


def _iter_test_functions(tree: ast.AST, rel: str) -> list[dict[str, Any]]:
    tests = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            tests.append({"node": node, "class_name": "", "nodeid": f"{rel}::{node.name}"})
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name.startswith("test_"):
                    tests.append({"node": child, "class_name": node.name, "nodeid": f"{rel}::{node.name}::{child.name}"})
    return tests


def _case_payload(item: dict[str, Any], rel: str, module_imports: list[str], config: dict[str, Any]) -> dict[str, Any]:
    node: ast.FunctionDef | ast.AsyncFunctionDef = item["node"]
    nodeid = item["nodeid"]
    markers = _markers(node)
    design_marker = markers.get("design", {})
    target_modules = sorted(set(module_imports) | _target_modules_from_imports(node) | _target_modules_from_strings(node))
    risks = _risks(rel, node.name, config, design_marker)
    specs = _specs(rel, risks, config, design_marker)
    domain = _domain(rel, node.name, config, design_marker)
    kind = _kind(rel, node.name, node, design_marker)
    smells: list[str] = []
    assert_count = sum(isinstance(child, ast.Assert) for child in ast.walk(node))
    raises_count = _call_count(node, {"pytest.raises", "raises"})
    mock_count = _mock_count(node)
    fixtures = [arg.arg for arg in node.args.args if arg.arg not in {"self", "cls"}]
    if assert_count == 0 and raises_count == 0:
        smells.append("no_assertions")
    if not target_modules:
        smells.append("no_target")
    if not specs:
        smells.append("no_spec")
    if mock_count >= 4:
        smells.append("heavy_mock")
    if len(fixtures) >= 7:
        smells.append("fixture_heavy")
    return {
        "nodeid": nodeid,
        "file": rel,
        "name": node.name,
        "line": int(getattr(node, "lineno", 0) or 0),
        "kind": kind,
        "domain": domain,
        "risks": risks,
        "target_modules": target_modules,
        "specs": specs,
        "fixtures": fixtures,
        "markers": sorted(markers),
        "assert_count": int(assert_count),
        "raises_count": int(raises_count),
        "mock_count": int(mock_count),
        "smells": smells,
    }


def _syntax_error_case(rel: str, exc: SyntaxError) -> dict[str, Any]:
    return {
        "nodeid": f"{rel}::<syntax_error>",
        "file": rel,
        "name": "<syntax_error>",
        "line": int(exc.lineno or 0),
        "kind": "architecture",
        "domain": "unclassified",
        "risks": ["test_suite_health"],
        "target_modules": [],
        "specs": [],
        "fixtures": [],
        "markers": [],
        "assert_count": 0,
        "raises_count": 0,
        "mock_count": 0,
        "smells": ["syntax_error"],
    }


def _markers(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, dict[str, Any]]:
    markers: dict[str, dict[str, Any]] = {}
    for decorator in node.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        expr = call.func if call else decorator
        name = _full_name(expr)
        if not name.startswith("pytest.mark."):
            continue
        key = name.rsplit(".", 1)[-1]
        values: dict[str, Any] = {}
        if call:
            for keyword in call.keywords:
                values[str(keyword.arg)] = _literal(keyword.value)
        markers[key] = values
    return markers


def _target_modules_from_imports(tree: ast.AST, top_level_only: bool = False) -> set[str]:
    modules: set[str] = set()
    nodes = getattr(tree, "body", []) if top_level_only else ast.walk(tree)
    for node in nodes:
        if isinstance(node, ast.Import):
            for alias in node.names:
                _add_target_module(modules, alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            _add_target_module(modules, node.module)
    return modules


def _target_modules_from_strings(node: ast.AST) -> set[str]:
    modules: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            value = child.value
            if "." in value:
                _add_target_module(modules, value.split(":", 1)[0])
    return modules


def _add_target_module(modules: set[str], raw: str) -> None:
    parts = [part for part in raw.split(".") if part]
    if not parts or parts[0] in STD_MODULES or parts[0] in {"pytest", "fastapi"}:
        return
    if parts[0] not in PRODUCTION_ROOTS:
        return
    length = min(len(parts), 3)
    modules.add(".".join(parts[:length]))


def _domain(rel: str, name: str, config: dict[str, Any], marker: dict[str, Any]) -> str:
    if marker.get("domain"):
        return str(marker["domain"])
    token = f"{rel}::{name}".lower()
    for raw in config.get("domains", []) or []:
        patterns = [str(item).lower() for item in raw.get("patterns", []) or []]
        if any(fnmatch.fnmatch(rel.lower(), pattern) or fnmatch.fnmatch(token, pattern) for pattern in patterns):
            return str(raw.get("key") or "unclassified")
    return "unclassified"


def _risks(rel: str, name: str, config: dict[str, Any], marker: dict[str, Any]) -> list[str]:
    if marker.get("risk"):
        return _as_list(marker["risk"])
    token = f"{rel}::{name}".lower()
    risks = []
    for raw in config.get("risks", []) or []:
        patterns = [str(item).lower() for item in raw.get("patterns", []) or []]
        if any(fnmatch.fnmatch(token, pattern) or pattern.strip("*") in token for pattern in patterns):
            risks.append(str(raw.get("key")))
    if risks:
        return sorted(set(risks))
    fallback = _fallback_risk(token)
    return [fallback] if fallback else ["general_behavior"]


def _fallback_risk(token: str) -> str:
    rules = {
        "pit_leakage": ("pit", "asof", "leakage", "reproducibility"),
        "architecture_drift": ("architecture", "layout", "modularization", "compat", "legacy"),
        "api_contract": ("api", "route", "web", "auth", "websocket"),
        "data_contract": ("datahub", "data_", "tushare", "provider", "quality", "price", "risk_free"),
        "strategy_governance": ("strategy", "candidate", "factor", "registry", "buffett", "ml_lgbm"),
        "backtest_validity": ("backtest", "pipeline", "regime", "hmm"),
        "execution_safety": ("execution", "broker", "order", "ledger", "fill"),
        "config_secret": ("env_secret", "settings", "config"),
        "docs_drift": ("docs", "documentation", "wiki", "acceptance"),
        "codegraph_design": ("codegraph",),
    }
    for key, needles in rules.items():
        if any(needle in token for needle in needles):
            return key
    return ""


def _specs(rel: str, risks: list[str], config: dict[str, Any], marker: dict[str, Any]) -> list[str]:
    specs: set[str] = set(_as_list(marker.get("spec")))
    for domain in config.get("domains", []) or []:
        patterns = [str(item).lower() for item in domain.get("patterns", []) or []]
        if any(fnmatch.fnmatch(rel.lower(), pattern) for pattern in patterns):
            specs.update(str(item) for item in domain.get("specs", []) or [])
    risk_map = {str(item.get("key")): item for item in config.get("risks", []) or []}
    for risk in risks:
        specs.update(str(item) for item in risk_map.get(risk, {}).get("specs", []) or [])
    return sorted(spec for spec in specs if spec)


def _kind(rel: str, name: str, node: ast.AST, marker: dict[str, Any]) -> str:
    explicit = str(marker.get("kind") or "")
    if explicit in TEST_KINDS:
        return explicit
    token = f"{rel}::{name}".lower()
    if "architecture" in token or "layout" in token or "modularization" in token:
        return "architecture"
    if "contract" in token:
        return "contract"
    if "route" in token or "api" in token or _call_count(node, {"TestClient"}):
        return "api"
    if "websocket" in token or "browser" in token or "frontend" in token:
        return "e2e"
    if _call_count(node, {"subprocess.run", "run_cli"}) or "integration" in token:
        return "integration"
    return "unit"


def _call_count(node: ast.AST, names: set[str]) -> int:
    count = 0
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            full = _full_name(child.func)
            short = full.rsplit(".", 1)[-1]
            if full in names or short in names:
                count += 1
    return count


def _mock_count(node: ast.AST) -> int:
    names = {"monkeypatch.setattr", "patch", "mock.patch", "MagicMock", "Mock"}
    count = _call_count(node, names)
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "monkeypatch":
            count += 1
    return count


def _full_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _full_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _literal(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]
    return [str(value)] if str(value) else []


def _diagnose_design(cases: list[dict[str, Any]], file_counts: Counter[str], config: dict[str, Any]) -> list[dict[str, Any]]:
    smells = []
    for case in cases:
        for smell in case["smells"]:
            smells.append(_smell(case["nodeid"], smell, case["file"], _case_smell_severity(smell), {"line": case["line"]}))
    for file, count in file_counts.items():
        if count >= 18:
            smells.append(_smell(file, "broad_test_file", file, "P2", {"test_count": count}))
    risk_counts = Counter(risk for case in cases for risk in case["risks"])
    for raw in config.get("risks", []) or []:
        key = str(raw.get("key") or "")
        if key and int(raw.get("required", 1)) and risk_counts[key] == 0:
            smells.append(_smell(key, "risk_without_tests", "", "P1", {"risk": key}))
    spec_counts = Counter(spec for case in cases for spec in case["specs"])
    known_specs = {str(spec) for domain in config.get("domains", []) or [] for spec in domain.get("specs", []) or []}
    for spec in sorted(known_specs):
        if spec and spec_counts[spec] == 0:
            smells.append(_smell(spec, "spec_without_tests", spec, "P2", {"spec": spec}))
    return smells


def _case_smell_severity(smell: str) -> str:
    return {
        "syntax_error": "P0",
        "no_assertions": "P1",
        "no_target": "P1",
        "no_spec": "P2",
        "heavy_mock": "P2",
        "fixture_heavy": "P2",
    }.get(smell, "P2")


def _smell(subject: str, kind: str, path: str, severity: str, evidence: dict[str, Any]) -> dict[str, Any]:
    titles = {
        "syntax_error": "Test file cannot be parsed",
        "no_assertions": "Test has no explicit assertion",
        "no_target": "Test is not linked to production code",
        "no_spec": "Test is not linked to a spec",
        "heavy_mock": "Test relies heavily on mocks",
        "fixture_heavy": "Test uses many fixtures",
        "broad_test_file": "Test file covers too many cases",
        "risk_without_tests": "Declared risk has no tests",
        "spec_without_tests": "Declared spec has no linked tests",
    }
    recommendations = {
        "syntax_error": "Fix the syntax error so pytest and design collection can inspect the file.",
        "no_assertions": "Add an explicit assertion or pytest.raises expectation for the behavior under test.",
        "no_target": "Import or reference the production module being verified so coverage can be reviewed.",
        "no_spec": "Map the test to a domain or pytest.mark.design(spec=...) entry.",
        "heavy_mock": "Add at least one lower-mock contract or integration test for the same behavior.",
        "fixture_heavy": "Split setup or move unrelated checks into focused tests.",
        "broad_test_file": "Split unrelated domains into smaller test files.",
        "risk_without_tests": "Add focused tests for this risk or remove the stale risk declaration.",
        "spec_without_tests": "Link at least one test to this spec through config or pytest.mark.design.",
    }
    return {
        "id": f"{kind}:{subject}",
        "severity": severity,
        "kind": kind,
        "title": titles.get(kind, kind.replace("_", " ").title()),
        "subject": subject,
        "path": path,
        "evidence": evidence,
        "recommendation": recommendations.get(kind, "Review this test design signal."),
    }


def _matrix_payload(cases: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    configured = [str(item.get("key")) for item in config.get("risks", []) or [] if item.get("key")]
    risks = sorted(set(configured) | {risk for case in cases for risk in case["risks"]})
    labels = {str(item.get("key")): item for item in config.get("risks", []) or []}
    rows = []
    for risk in risks:
        counts = {kind: 0 for kind in TEST_KINDS}
        for case in cases:
            if risk in case["risks"] and case["kind"] in counts:
                counts[case["kind"]] += 1
        raw = labels.get(risk, {})
        rows.append({
            "key": risk,
            "label_zh": str(raw.get("label_zh") or risk),
            "label_en": str(raw.get("label_en") or risk),
            "counts": counts,
            "total": sum(counts.values()),
        })
    return {"kinds": list(TEST_KINDS), "risks": rows}


def _graph_payload(cases: list[dict[str, Any]], smells: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    links: Counter[tuple[str, str, str]] = Counter()

    def add_node(node_id: str, label: str, kind: str, group: str, path: str = "") -> None:
        nodes.setdefault(node_id, {"id": node_id, "label": label, "kind": kind, "group": group, "path": path, "count": 0})
        nodes[node_id]["count"] += 1

    def add_link(source: str, target: str, kind: str) -> None:
        links[(source, target, kind)] += 1

    for case in cases:
        case_id = f"test:{case['nodeid']}"
        file_id = f"file:{case['file']}"
        add_node(file_id, case["file"], "test_file", case["domain"], case["file"])
        add_node(case_id, case["name"], "test_case", case["domain"], case["file"])
        add_link(file_id, case_id, "contains")
        for risk in case["risks"]:
            risk_id = f"risk:{risk}"
            add_node(risk_id, risk, "risk", "risk")
            add_link(risk_id, case_id, "tests")
        for target in case["target_modules"]:
            target_id = f"target:{target}"
            add_node(target_id, target, "target_module", "target")
            add_link(case_id, target_id, "covers")
        for spec in case["specs"]:
            spec_id = f"spec:{spec}"
            add_node(spec_id, spec.rsplit("/", 1)[-1], "spec", "spec", spec)
            add_link(case_id, spec_id, "documents")
        for fixture in case["fixtures"]:
            fixture_id = f"fixture:{fixture}"
            add_node(fixture_id, fixture, "fixture", "fixture")
            add_link(case_id, fixture_id, "uses")
    for smell in smells:
        smell_id = f"smell:{smell['id']}"
        add_node(smell_id, smell["kind"], "smell", smell["severity"], smell["path"])
    return {
        "nodes": sorted(nodes.values(), key=lambda item: (item["kind"], item["id"])),
        "links": [
            {"source": source, "target": target, "type": kind, "label": kind, "count": count}
            for (source, target, kind), count in sorted(links.items())
        ],
    }


def _summary_payload(cases: list[dict[str, Any]], smells: list[dict[str, Any]], matrix: dict[str, Any], files: list[Path]) -> dict[str, Any]:
    total = len(cases)
    risk_total = len(matrix["risks"])
    risk_covered = sum(1 for row in matrix["risks"] if row["total"] > 0)
    target_linked = sum(1 for case in cases if case["target_modules"])
    spec_linked = sum(1 for case in cases if case["specs"])
    severity = Counter(smell["severity"] for smell in smells)
    weighted_smells = severity["P0"] * 5.0 + severity["P1"] * 2.0 + severity["P2"] * 0.7
    penalty = (weighted_smells / max(total, 1)) * 100
    score = round(max(0, min(100, 100 - penalty)))
    return {
        "test_count": total,
        "file_count": len(files),
        "target_count": len({target for case in cases for target in case["target_modules"]}),
        "spec_count": len({spec for case in cases for spec in case["specs"]}),
        "risk_count": risk_total,
        "risk_covered": risk_covered,
        "risk_coverage_rate": risk_covered / risk_total if risk_total else 0.0,
        "target_link_rate": target_linked / total if total else 0.0,
        "spec_link_rate": spec_linked / total if total else 0.0,
        "smell_count": len(smells),
        "severity_counts": dict(severity),
        "design_score": score,
        "truncated": False,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
