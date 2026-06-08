import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


def _make_codegraph_db(project_root: Path) -> Path:
    graph_dir = project_root / ".codegraph"
    graph_dir.mkdir()
    db_path = graph_dir / "codegraph.db"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            language TEXT NOT NULL,
            size INTEGER NOT NULL,
            modified_at INTEGER NOT NULL,
            indexed_at INTEGER NOT NULL,
            node_count INTEGER DEFAULT 0,
            errors TEXT
        );
        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            language TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            start_column INTEGER NOT NULL,
            end_column INTEGER NOT NULL,
            docstring TEXT,
            signature TEXT,
            visibility TEXT,
            is_exported INTEGER DEFAULT 0,
            is_async INTEGER DEFAULT 0,
            is_static INTEGER DEFAULT 0,
            is_abstract INTEGER DEFAULT 0,
            decorators TEXT,
            type_parameters TEXT,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            kind TEXT NOT NULL,
            metadata TEXT,
            line INTEGER,
            col INTEGER,
            provenance TEXT DEFAULT NULL
        );
        """
    )
    files = [
        ("data/storage/datahub.py", "h1", "python", 4000, 1, 2, 3, "[]"),
        ("web/api/routes/codegraph.py", "h2", "python", 2200, 1, 2, 2, "[]"),
        ("web/frontend/src/views/CodeGraph.vue", "h3", "vue", 1800, 1, 2, 1, "[]"),
    ]
    con.executemany("INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?)", files)
    nodes = [
        ("file:data/storage/datahub.py", "file", "datahub.py", "data/storage/datahub.py", "data/storage/datahub.py", "python", 1, 120, 0, 0, None, None),
        ("class:datahub", "class", "DataHub", "DataHub", "data/storage/datahub.py", "python", 10, 80, 0, 0, "storage facade", "class DataHub"),
        ("func:get_datahub", "function", "get_datahub", "get_datahub", "data/storage/datahub.py", "python", 90, 95, 0, 0, None, "get_datahub()"),
        ("file:web/api/routes/codegraph.py", "file", "codegraph.py", "web/api/routes/codegraph.py", "web/api/routes/codegraph.py", "python", 1, 90, 0, 0, None, None),
        ("func:codegraph_status", "function", "codegraph_status", "codegraph_status", "web/api/routes/codegraph.py", "python", 20, 28, 0, 0, None, "codegraph_status()"),
        ("file:web/frontend/src/views/CodeGraph.vue", "file", "CodeGraph.vue", "web/frontend/src/views/CodeGraph.vue", "web/frontend/src/views/CodeGraph.vue", "vue", 1, 50, 0, 0, None, None),
        ("component:codegraph", "component", "CodeGraph", "web/frontend/src/views/CodeGraph.vue::CodeGraph", "web/frontend/src/views/CodeGraph.vue", "vue", 1, 50, 0, 0, None, None),
    ]
    con.executemany(
        """
        INSERT INTO nodes (
            id, kind, name, qualified_name, file_path, language, start_line, end_line,
            start_column, end_column, docstring, signature, visibility, is_exported,
            is_async, is_static, is_abstract, decorators, type_parameters, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, 0, 0, 0, '[]', '[]', 3)
        """,
        nodes,
    )
    edges = [
        ("file:data/storage/datahub.py", "class:datahub", "contains", None, None, None, None),
        ("file:data/storage/datahub.py", "func:get_datahub", "contains", None, None, None, None),
        ("file:web/api/routes/codegraph.py", "func:codegraph_status", "contains", None, None, None, None),
        ("file:web/frontend/src/views/CodeGraph.vue", "component:codegraph", "contains", None, None, None, None),
        ("func:codegraph_status", "func:get_datahub", "calls", '{"confidence":0.9}', 25, 4, None),
        ("component:codegraph", "func:codegraph_status", "references", '{"confidence":0.7}', 30, 2, None),
    ]
    con.executemany(
        "INSERT INTO edges (source, target, kind, metadata, line, col, provenance) VALUES (?, ?, ?, ?, ?, ?, ?)",
        edges,
    )
    con.commit()
    con.close()
    return db_path


def test_codegraph_service_builds_module_file_and_symbol_graphs(tmp_path):
    from web.api.services.codegraph import CodeGraphService

    _make_codegraph_db(tmp_path)
    service = CodeGraphService(tmp_path)

    status = service.status()
    assert status["initialized"] is True
    assert status["file_count"] == 3
    assert status["node_count"] == 7
    assert status["edge_count"] == 6
    assert status["stale"] is False

    module_graph = service.graph(level="module")
    module_ids = {node["id"] for node in module_graph["nodes"]}
    assert {"module:data", "module:web"} <= module_ids
    assert all(link["type"] != "contains" for link in module_graph["links"])
    assert any(link["source"] == "module:web" and link["target"] == "module:data" for link in module_graph["links"])

    file_graph = service.graph(level="file", root="data")
    file_ids = {node["id"] for node in file_graph["nodes"]}
    assert "file:data/storage/datahub.py" in file_ids
    assert "external:web" in file_ids
    assert any(link["source"] == "external:web" and link["target"] == "file:data/storage/datahub.py" for link in file_graph["links"])

    symbol_graph = service.graph(level="symbol", root="data/storage/datahub.py")
    symbol_ids = {node["id"] for node in symbol_graph["nodes"]}
    assert {"file:data/storage/datahub.py", "class:datahub", "func:get_datahub"} <= symbol_ids
    assert any(link["type"] == "contains" for link in symbol_graph["links"])


def test_codegraph_services_share_common_path_helpers():
    from web.api.services import codegraph, codegraph_diagnostics

    for module in (codegraph, codegraph_diagnostics):
        assert "_bounded_limit" not in module.__dict__
        assert "_top_module" not in module.__dict__


def test_codegraph_search_and_neighborhood_are_limited(tmp_path):
    from web.api.services.codegraph import CodeGraphService

    _make_codegraph_db(tmp_path)
    service = CodeGraphService(tmp_path)

    results = service.search("DataHub", limit=5)
    assert results[0]["id"] == "class:datahub"
    assert results[0]["path"] == "data/storage/datahub.py"

    graph = service.neighborhood("func:codegraph_status", depth=1, limit=10)
    ids = {node["id"] for node in graph["nodes"]}
    assert {"func:codegraph_status", "func:get_datahub"} <= ids
    assert any(link["source"] == "func:codegraph_status" and link["target"] == "func:get_datahub" for link in graph["links"])


def test_codegraph_sync_uses_fixed_commands_and_lock(tmp_path, monkeypatch):
    from web.api.services import codegraph

    calls = []

    def fake_run(args, cwd, text, capture_output, timeout, check):
        calls.append((args, cwd, text, capture_output, timeout, check))
        return codegraph.CodeGraphCommandResult(args=args, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(codegraph.subprocess, "run", fake_run)

    sync = codegraph.run_codegraph_sync(tmp_path, "sync")
    rebuild = codegraph.run_codegraph_sync(tmp_path, "rebuild")

    assert sync["status"] == "ok"
    assert rebuild["status"] == "ok"
    assert calls[0][0] == ["codegraph", "sync", str(tmp_path)]
    assert calls[1][0] == ["codegraph", "uninit", "--force", str(tmp_path)]
    assert calls[2][0] == ["codegraph", "init", str(tmp_path)]
    assert calls[3][0] == ["codegraph", "index", str(tmp_path)]
    assert all(call[1] == tmp_path for call in calls)


def test_codegraph_api_serves_status_and_graph(monkeypatch, tmp_path):
    from web.api.app import create_app
    from web.api.routes import codegraph as route

    _make_codegraph_db(tmp_path)
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setattr(route, "PROJECT_ROOT", tmp_path)

    client = TestClient(create_app())

    status = client.get("/api/codegraph/status")
    graph = client.get("/api/codegraph/graph?level=module")

    assert status.status_code == 200
    assert status.json()["file_count"] == 3
    assert graph.status_code == 200
    assert graph.json()["nodes"]


def _make_diagnostics_db(project_root: Path) -> Path:
    graph_dir = project_root / ".codegraph"
    graph_dir.mkdir()
    db_path = graph_dir / "codegraph.db"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            language TEXT NOT NULL,
            size INTEGER NOT NULL,
            modified_at INTEGER NOT NULL,
            indexed_at INTEGER NOT NULL,
            node_count INTEGER DEFAULT 0,
            errors TEXT
        );
        CREATE TABLE nodes (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            language TEXT NOT NULL,
            start_line INTEGER NOT NULL,
            end_line INTEGER NOT NULL,
            start_column INTEGER NOT NULL,
            end_column INTEGER NOT NULL,
            docstring TEXT,
            signature TEXT,
            visibility TEXT,
            is_exported INTEGER DEFAULT 0,
            is_async INTEGER DEFAULT 0,
            is_static INTEGER DEFAULT 0,
            is_abstract INTEGER DEFAULT 0,
            decorators TEXT,
            type_parameters TEXT,
            updated_at INTEGER NOT NULL
        );
        CREATE TABLE edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            kind TEXT NOT NULL,
            metadata TEXT,
            line INTEGER,
            col INTEGER,
            provenance TEXT DEFAULT NULL
        );
        """
    )
    files = [
        ("web/api/routes/bad.py", "h1", "python", 2500, 1, 2, 2, "[]"),
        ("data/storage/internal.py", "h2", "python", 9000, 1, 2, 6, "[]"),
        ("pipeline/a.py", "h3", "python", 1800, 1, 2, 2, "[]"),
        ("pipeline/b.py", "h4", "python", 1800, 1, 2, 2, "[]"),
        ("scripts/entry.py", "h5", "python", 1200, 1, 2, 1, "[]"),
        ("models/unused.py", "h6", "python", 1200, 1, 2, 1, "[]"),
        ("web/frontend/src/views/BigView.vue", "h7", "vue", 40000, 1, 2, 20, "[]"),
    ]
    con.executemany("INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?)", files)
    nodes = [
        ("file:web/api/routes/bad.py", "file", "bad.py", "web/api/routes/bad.py", "web/api/routes/bad.py", "python", 1, 120),
        ("func:web_route", "function", "web_route", "web_route", "web/api/routes/bad.py", "python", 10, 50),
        ("file:data/storage/internal.py", "file", "internal.py", "data/storage/internal.py", "data/storage/internal.py", "python", 1, 820),
        ("func:internal_api", "function", "internal_api", "internal_api", "data/storage/internal.py", "python", 20, 80),
        ("func:hot_a", "function", "hot_a", "hot_a", "data/storage/internal.py", "python", 120, 180),
        ("func:hot_b", "function", "hot_b", "hot_b", "data/storage/internal.py", "python", 200, 260),
        ("file:pipeline/a.py", "file", "a.py", "pipeline/a.py", "pipeline/a.py", "python", 1, 90),
        ("func:a", "function", "a", "a", "pipeline/a.py", "python", 10, 30),
        ("file:pipeline/b.py", "file", "b.py", "pipeline/b.py", "pipeline/b.py", "python", 1, 90),
        ("func:b", "function", "b", "b", "pipeline/b.py", "python", 10, 30),
        ("file:scripts/entry.py", "file", "entry.py", "scripts/entry.py", "scripts/entry.py", "python", 1, 70),
        ("func:entry", "function", "entry", "entry", "scripts/entry.py", "python", 5, 40),
        ("file:models/unused.py", "file", "unused.py", "models/unused.py", "models/unused.py", "python", 1, 60),
        ("func:unused", "function", "unused", "unused", "models/unused.py", "python", 5, 20),
        ("file:web/frontend/src/views/BigView.vue", "file", "BigView.vue", "web/frontend/src/views/BigView.vue", "web/frontend/src/views/BigView.vue", "vue", 1, 980),
        ("component:big", "component", "BigView", "BigView", "web/frontend/src/views/BigView.vue", "vue", 1, 980),
    ]
    con.executemany(
        """
        INSERT INTO nodes (
            id, kind, name, qualified_name, file_path, language, start_line, end_line,
            start_column, end_column, docstring, signature, visibility, is_exported,
            is_async, is_static, is_abstract, decorators, type_parameters, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, '[]', '[]', 3)
        """,
        nodes,
    )
    edges = [
        ("file:web/api/routes/bad.py", "func:web_route", "contains", None, None, None, None),
        ("file:data/storage/internal.py", "func:internal_api", "contains", None, None, None, None),
        ("file:data/storage/internal.py", "func:hot_a", "contains", None, None, None, None),
        ("file:data/storage/internal.py", "func:hot_b", "contains", None, None, None, None),
        ("file:pipeline/a.py", "func:a", "contains", None, None, None, None),
        ("file:pipeline/b.py", "func:b", "contains", None, None, None, None),
        ("file:scripts/entry.py", "func:entry", "contains", None, None, None, None),
        ("file:models/unused.py", "func:unused", "contains", None, None, None, None),
        ("file:web/frontend/src/views/BigView.vue", "component:big", "contains", None, None, None, None),
        ("func:web_route", "func:internal_api", "imports", None, 12, 4, None),
        ("func:entry", "func:internal_api", "references", None, 8, 1, None),
        ("component:big", "func:internal_api", "references", None, 40, 2, None),
        ("func:a", "func:b", "imports", None, 20, 1, None),
        ("func:b", "func:a", "imports", None, 20, 1, None),
        ("func:internal_api", "func:hot_a", "calls", None, 70, 1, None),
        ("func:internal_api", "func:hot_b", "calls", None, 72, 1, None),
        ("component:big", "func:hot_a", "calls", None, 100, 2, None),
        ("func:web_route", "func:hot_b", "calls", None, 25, 4, None),
    ]
    con.executemany(
        "INSERT INTO edges (source, target, kind, metadata, line, col, provenance) VALUES (?, ?, ?, ?, ?, ?, ?)",
        edges,
    )
    con.commit()
    con.close()
    return db_path


def test_codegraph_diagnostics_detects_architecture_risks(tmp_path, monkeypatch):
    from web.api.services.codegraph_diagnostics import CodeGraphDiagnosticsService

    _make_diagnostics_db(tmp_path)
    service = CodeGraphDiagnosticsService(tmp_path)
    monkeypatch.setattr(service, "_git_churn", lambda: {"data/storage/internal.py": 7})

    payload = service.diagnostics(limit=40, include_git=True)
    categories = {issue["category"] for issue in payload["issues"]}

    assert payload["summary"]["initialized"] is True
    assert payload["summary"]["issue_count"] == len(payload["issues"])
    assert payload["summary"]["git_churn_available"] is True
    assert {"cycle", "cross_layer", "hotspot", "orphan", "internal_api_leak", "large_connected_file"} <= categories
    assert any(issue["source"] == "web/api/routes/bad.py" and issue["target"] == "data/storage/internal.py" for issue in payload["issues"])
    assert payload["node_scores"]["file:data/storage/internal.py"]["severity"] in {"P0", "P1"}
    assert any(flag["category"] == "cross_layer" for flag in payload["edge_flags"])


def test_codegraph_diagnostics_keeps_entrypoints_tests_and_facades_below_p0(tmp_path, monkeypatch):
    from web.api.services.codegraph_diagnostics import CodeGraphDiagnosticsService

    _make_diagnostics_db(tmp_path)
    service = CodeGraphDiagnosticsService(tmp_path)
    monkeypatch.setattr(
        service,
        "_git_churn",
        lambda: {
            "scripts/entry.py": 30,
            "tests/test_contract.py": 30,
            "data/storage/datahub.py": 1,
            "models/__init__.py": 12,
        },
    )
    con = sqlite3.connect(tmp_path / ".codegraph" / "codegraph.db")
    con.executemany(
        "INSERT INTO files VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("tests/test_contract.py", "h8", "python", 9000, 1, 2, 4, "[]"),
            ("data/storage/datahub.py", "h9", "python", 12000, 1, 2, 10, "[]"),
            ("models/__init__.py", "h10", "python", 2000, 1, 2, 3, "[]"),
        ],
    )
    con.executemany(
        """
        INSERT INTO nodes (
            id, kind, name, qualified_name, file_path, language, start_line, end_line,
            start_column, end_column, docstring, signature, visibility, is_exported,
            is_async, is_static, is_abstract, decorators, type_parameters, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, '[]', '[]', 3)
        """,
        [
            ("file:tests/test_contract.py", "file", "test_contract.py", "tests/test_contract.py", "tests/test_contract.py", "python", 1, 620),
            ("func:test_contract", "function", "test_contract", "test_contract", "tests/test_contract.py", "python", 20, 80),
            ("file:data/storage/datahub.py", "file", "datahub.py", "data/storage/datahub.py", "data/storage/datahub.py", "python", 1, 520),
            ("func:datahub", "function", "get_datahub", "get_datahub", "data/storage/datahub.py", "python", 20, 80),
            ("file:models/__init__.py", "file", "__init__.py", "models/__init__.py", "models/__init__.py", "python", 1, 40),
            ("func:model_api", "function", "model_api", "model_api", "models/__init__.py", "python", 5, 20),
            ("func:test_user", "function", "test_user", "test_user", "tests/test_contract.py", "python", 90, 120),
        ],
    )
    noisy_edges = []
    noisy_edges.extend(("func:test_contract", "func:datahub", "calls", None, 10, 1, None) for _ in range(60))
    noisy_edges.extend(("func:entry", "func:datahub", "calls", None, 11, 1, None) for _ in range(6))
    noisy_edges.extend(("func:web_route", "func:datahub", "calls", None, 12, 1, None) for _ in range(90))
    noisy_edges.extend(("func:test_user", "func:model_api", "calls", None, 13, 1, None) for _ in range(40))
    con.executemany(
        "INSERT INTO edges (source, target, kind, metadata, line, col, provenance) VALUES (?, ?, ?, ?, ?, ?, ?)",
        noisy_edges,
    )
    con.commit()
    con.close()

    payload = service.diagnostics(limit=80, include_git=True)
    issues = {issue["path"]: issue for issue in payload["issues"] if issue["category"] == "hotspot"}

    assert "tests/test_contract.py" not in issues
    assert issues["scripts/entry.py"]["severity"] != "P0"
    assert issues["data/storage/datahub.py"]["severity"] != "P0"
    assert all(issue["category"] != "internal_api_leak" or issue["path"] != "models/__init__.py" for issue in payload["issues"])


def test_codegraph_diagnostics_limit_and_api_contract(tmp_path, monkeypatch):
    from web.api.app import create_app
    from web.api.routes import codegraph as route

    _make_diagnostics_db(tmp_path)
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setattr(route, "PROJECT_ROOT", tmp_path)

    client = TestClient(create_app())
    res = client.get("/api/codegraph/diagnostics?limit=2&include_git=false")

    assert res.status_code == 200
    payload = res.json()
    assert payload["summary"]["initialized"] is True
    assert payload["summary"]["truncated"] is True
    assert payload["summary"]["git_churn_available"] is False
    assert len(payload["issues"]) == 2
    assert "node_scores" in payload
    assert "edge_flags" in payload
