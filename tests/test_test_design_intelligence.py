import json
import textwrap


def test_collect_test_design_uses_ast_without_importing_tests(tmp_path):
    from astrolabe_cli.design_intelligence import collect_test_design

    project = tmp_path
    tests_dir = project / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample_contracts.py").write_text(
        textwrap.dedent(
            '''
            raise RuntimeError("collector imported this module")

            import pytest
            from data.storage.datahub import DataHub
            from web.api.app import create_app

            @pytest.mark.design(risk="api_contract", kind="api", spec="docs/specs/05-web-platform.md")
            def test_api_contract(monkeypatch, tmp_path):
                monkeypatch.setattr("web.api.auth.get_api_key", lambda: "")
                with pytest.raises(ValueError):
                    raise ValueError("unit")
                assert DataHub is not None
                assert create_app is not None
            '''
        ),
        encoding="utf-8",
    )
    config = {
        "design": {"scan_globs": ["tests/test*.py"]},
        "domains": [
            {
                "key": "web_system",
                "label_zh": "Web / System",
                "label_en": "Web / System",
                "patterns": ["tests/test_*contract*.py"],
                "modules": ["web/api/"],
                "specs": ["docs/specs/05-web-platform.md"],
            }
        ],
        "risks": [
            {
                "key": "api_contract",
                "label_zh": "API 合约",
                "label_en": "API Contract",
                "patterns": ["*api*", "*contract*"],
                "specs": ["docs/specs/05-web-platform.md"],
            }
        ],
    }

    payload = collect_test_design(project, config)

    assert payload["status"] == "ok"
    assert payload["summary"]["test_count"] == 1
    case = payload["cases"][0]
    assert case["nodeid"] == "tests/test_sample_contracts.py::test_api_contract"
    assert case["kind"] == "api"
    assert case["domain"] == "web_system"
    assert "api_contract" in case["risks"]
    assert "docs/specs/05-web-platform.md" in case["specs"]
    assert "monkeypatch" in case["fixtures"]
    assert case["assert_count"] == 2
    assert case["raises_count"] == 1
    assert case["mock_count"] >= 1
    assert "data.storage.datahub" in case["target_modules"]
    assert "web.api.app" in case["target_modules"]
    assert payload["matrix"]["risks"][0]["counts"]["api"] == 1
    assert any(edge["type"] == "tests" for edge in payload["graph"]["links"])


def test_collect_test_design_returns_stable_empty_payload(tmp_path):
    from astrolabe_cli.design_intelligence import collect_test_design

    payload = collect_test_design(tmp_path, {"design": {"scan_globs": ["tests/test*.py"]}, "risks": []})

    assert payload["status"] == "empty"
    assert payload["summary"]["test_count"] == 0
    assert payload["cases"] == []
    assert payload["matrix"]["risks"] == []


def test_collect_test_design_counts_pandas_testing_assertions(tmp_path):
    from astrolabe_cli.design_intelligence import collect_test_design

    project = tmp_path
    tests_dir = project / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_pandas_assert.py").write_text(
        textwrap.dedent(
            """
            import pandas as pd

            def test_frame_contract():
                left = pd.DataFrame({"x": [1]})
                right = pd.DataFrame({"x": [1]})
                pd.testing.assert_frame_equal(left, right)
            """
        ),
        encoding="utf-8",
    )

    payload = collect_test_design(project, {"design": {"scan_globs": ["tests/test*.py"]}})

    assert payload["cases"][0]["assert_count"] == 1
    assert "no_assertions" not in payload["cases"][0]["smells"]


def test_write_test_design_artifact_uses_design_latest(monkeypatch, tmp_path):
    from data.storage.datahub import reset_datahub
    from astrolabe_cli.design_intelligence import write_test_design_artifact

    monkeypatch.setenv("ASTROLABE_VAR", str(tmp_path / "var"))
    reset_datahub()

    payload = {"status": "ok", "generated_at": "2026-06-07T00:00:00Z"}
    write_test_design_artifact(payload)

    latest = tmp_path / "var" / "artifacts" / "tests" / "design" / "latest.json"
    assert json.loads(latest.read_text(encoding="utf-8"))["status"] == "ok"
    reset_datahub()
