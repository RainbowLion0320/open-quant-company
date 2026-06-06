import json


def _json_from_cli(capsys):
    return json.loads(capsys.readouterr().out)


def test_strategy_catalog_command_outputs_items(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["strategy", "catalog", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["total"] >= 4
    assert any(item["name"] == "multifactor" for item in data["data"]["items"])


def test_strategy_run_dry_run_requires_explicit_research_for_candidate(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["strategy", "run", "trend_following", "--dry-run", "--json"])
    data = _json_from_cli(capsys)

    assert code == 1
    assert data["ok"] is False
    assert "research" in data["message"]


def test_strategy_run_research_dry_run_lists_candidate(capsys):
    from astrolabe_cli.main import run_cli

    code = run_cli(["strategy", "run", "trend_following", "--mode", "research", "--dry-run", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["data"]["dry_run"] is True
    assert data["data"]["would_run"]["strategy"] == "trend_following"
    assert data["data"]["would_run"]["mode"] == "research"


def test_strategy_evidence_without_name_lists_artifacts(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    monkeypatch.setattr(
        "research.strategy_evaluation.list_evidence_artifacts",
        lambda: [
            {
                "strategy": "trend_following",
                "path": "var/store/research/strategy_evidence/trend_following.json",
                "exists": False,
                "promotion_decision": "missing",
                "oos_status": "missing",
                "baseline_count": 0,
                "parse_error": None,
            }
        ],
    )

    code = run_cli(["strategy", "evidence", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["total"] == 1
    assert data["data"]["items"][0]["strategy"] == "trend_following"


def test_strategy_evidence_with_name_returns_detail(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    monkeypatch.setattr(
        "research.strategy_evaluation.load_evidence_artifact",
        lambda name: {
            "strategy": name,
            "exists": False,
            "path": f"var/store/research/strategy_evidence/{name}.json",
            "summary": {},
            "artifact": {},
            "parse_error": None,
        },
    )

    code = run_cli(["strategy", "evidence", "trend_following", "--json"])
    data = _json_from_cli(capsys)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["strategy"] == "trend_following"
    assert data["data"]["exists"] is False
