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


def test_codegraph_api_replaces_hindsight_graph_route(monkeypatch, tmp_path):
    from web.api.app import create_app
    from web.api.routes import codegraph as route

    _make_codegraph_db(tmp_path)
    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setattr(route, "PROJECT_ROOT", tmp_path)

    client = TestClient(create_app())

    status = client.get("/api/codegraph/status")
    graph = client.get("/api/codegraph/graph?level=module")
    old = client.get("/api/hindsight/graph")

    assert status.status_code == 200
    assert status.json()["file_count"] == 3
    assert graph.status_code == 200
    assert graph.json()["nodes"]
    assert old.status_code == 404
