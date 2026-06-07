import json
import textwrap

import pytest


def test_collect_ast_intelligence_detects_multilanguage_duplicates(tmp_path):
    from astrolabe_cli.ast_intelligence import collect_ast_intelligence

    project = tmp_path
    (project / "pkg").mkdir()
    (project / "pkg" / "alpha.py").write_text(
        textwrap.dedent(
            """
            def compute_alpha(left, right):
                total = left + right
                return total * 2

            def compute_beta(left, right):
                total = left + right
                return total * 2
            """
        ),
        encoding="utf-8",
    )
    (project / "web").mkdir()
    (project / "web" / "one.ts").write_text(
        "export function normalizeOne(value: number) { const total = value + 1; return total * 3; }\n",
        encoding="utf-8",
    )
    (project / "web" / "two.ts").write_text(
        "export function normalizeTwo(value: number) { const total = value + 1; return total * 3; }\n",
        encoding="utf-8",
    )
    (project / "web" / "Panel.vue").write_text(
        textwrap.dedent(
            """
            <template><section><button @click="save">Save</button></section></template>
            <script setup lang="ts">
            function save() {
              const total = 1 + 2
              return total * 4
            }
            </script>
            <style scoped>
            .primary { color: red; display: flex; gap: 8px; }
            .secondary { color: red; display: flex; gap: 8px; }
            </style>
            """
        ),
        encoding="utf-8",
    )

    payload = collect_ast_intelligence(project)

    assert payload["status"] == "ok"
    assert payload["recommended_command"] == "astroq architecture ast --json"
    assert payload["summary"]["file_count"] >= 4
    assert payload["summary"]["unit_count"] >= 6
    assert payload["summary"]["clone_group_count"] >= 2
    assert {"python", "typescript", "vue", "css"} <= set(payload["summary"]["languages"])
    categories = {issue["category"] for issue in payload["issues"]}
    assert "exact_clone" in categories
    assert "style_clone" in categories
    assert payload["graph"]["nodes"]
    assert payload["graph"]["links"]


def test_ast_intelligence_ignores_tiny_wrappers(tmp_path):
    from astrolabe_cli.ast_intelligence import collect_ast_intelligence

    project = tmp_path
    (project / "tiny.py").write_text(
        textwrap.dedent(
            """
            def one():
                return 1

            def two():
                return 1
            """
        ),
        encoding="utf-8",
    )

    payload = collect_ast_intelligence(project)

    assert payload["summary"]["issue_count"] == 0
    assert payload["summary"]["clone_group_count"] == 0


def test_ast_intelligence_frontend_parser_failure_is_explicit(monkeypatch, tmp_path):
    from astrolabe_cli.ast_intelligence import collect_ast_intelligence

    project = tmp_path
    (project / "broken.ts").write_text("export const value = 1;\n", encoding="utf-8")

    class GitCompleted:
        returncode = 1
        stdout = ""
        stderr = ""

    class NodeCompleted:
        returncode = 1
        stdout = ""
        stderr = "Cannot find module 'typescript'"

    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            return GitCompleted()
        if cmd[0] == "node":
            return NodeCompleted()
        raise AssertionError(cmd)

    monkeypatch.setattr("astrolabe_cli.ast_intelligence.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="Frontend AST parser failed"):
        collect_ast_intelligence(project)


def test_ast_intelligence_cli_writes_architecture_artifact(monkeypatch, tmp_path, capsys):
    from data.storage.datahub import reset_datahub
    from astrolabe_cli.main import run_cli

    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    reset_datahub()

    code = run_cli(["architecture", "ast", "--json"])
    data = json.loads(capsys.readouterr().out)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["status"] == "ok"
    assert data["data"]["summary"]["file_count"] >= 1

    artifact = tmp_path / "var" / "artifacts" / "architecture" / "ast" / "latest.json"
    latest = json.loads(artifact.read_text(encoding="utf-8"))
    assert latest["recommended_command"] == "astroq architecture ast --json"
    assert latest["summary"]["unit_count"] >= 1
    reset_datahub()


def test_ast_intelligence_cli_does_not_write_fake_artifact_on_parser_failure(monkeypatch, tmp_path, capsys):
    from astrolabe_cli.main import run_cli

    project = tmp_path / "project"
    project.mkdir()
    (project / "broken.ts").write_text("export const value = 1;\n", encoding="utf-8")
    artifact_root = tmp_path / "var" / "artifacts" / "architecture"

    class FakeHub:
        project_root = project

        def artifact_dir(self, kind):
            return artifact_root / kind

        def write_json(self, payload, path, indent=2):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=indent), encoding="utf-8")

    class GitCompleted:
        returncode = 1
        stdout = ""
        stderr = ""

    class NodeCompleted:
        returncode = 1
        stdout = ""
        stderr = "Cannot find module 'typescript'"

    def fake_run(cmd, **kwargs):
        if cmd[0] == "git":
            return GitCompleted()
        if cmd[0] == "node":
            return NodeCompleted()
        raise AssertionError(cmd)

    monkeypatch.setattr("astrolabe_cli.commands.architecture.get_datahub", lambda: FakeHub())
    monkeypatch.setattr("astrolabe_cli.ast_intelligence.subprocess.run", fake_run)

    code = run_cli(["architecture", "ast", "--json"])
    data = json.loads(capsys.readouterr().out)

    assert code == 1
    assert data["ok"] is False
    assert data["data"]["status"] == "error"
    assert "Frontend AST parser failed" in data["errors"][0]
    assert not (artifact_root / "ast" / "latest.json").exists()


def test_ast_intelligence_api_is_artifact_only(monkeypatch, tmp_path):
    from data.storage.datahub import get_datahub, reset_datahub
    from web.api.app import create_app
    from fastapi.testclient import TestClient

    monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("API must not scan")))
    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    reset_datahub()

    client = TestClient(create_app())
    missing = client.get("/api/system/ast-intelligence")
    assert missing.status_code == 200
    assert missing.json()["status"] == "no_artifact"
    assert missing.json()["recommended_command"] == "astroq architecture ast --json"

    artifact_dir = get_datahub().artifact_dir("architecture") / "ast"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "status": "ok",
        "generated_at": "2026-06-07T10:00:00Z",
        "recommended_command": "astroq architecture ast --json",
        "summary": {
            "file_count": 2,
            "unit_count": 3,
            "issue_count": 1,
            "clone_group_count": 1,
            "languages": {"python": 1, "typescript": 1},
            "severity_counts": {"P1": 1},
            "duplicate_score": 15,
        },
        "issues": [{"id": "exact_clone:g1", "severity": "P1", "category": "exact_clone", "title": "Exact clone", "paths": ["a.py"], "units": [], "language": "python", "evidence": {}, "recommendation": "Extract helper"}],
        "clone_groups": [{"id": "g1", "category": "exact_clone", "similarity": 1.0, "units": [], "shared_shape": "unit", "module_pairs": ["a:b"]}],
        "graph": {"nodes": [], "links": []},
    }
    (artifact_dir / "latest.json").write_text(json.dumps(payload), encoding="utf-8")

    present = client.get("/api/system/ast-intelligence")
    assert present.status_code == 200
    body = present.json()
    assert body["status"] == "ok"
    assert body["summary"]["duplicate_score"] == 15
    assert body["summary"]["artifact_age_seconds"] is not None
    assert body["clone_groups"][0]["id"] == "g1"
    reset_datahub()
