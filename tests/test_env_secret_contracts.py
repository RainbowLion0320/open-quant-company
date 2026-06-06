import json


def _json_from_cli(capsys):
    return json.loads(capsys.readouterr().out)


def test_env_secret_reader_uses_aliases_and_masks_values(monkeypatch):
    from core.env_secrets import read_env_secret, secret_status

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setenv("TUSHARE_PRO_TOKEN", "abcdefghijklmnop")

    assert read_env_secret("TUSHARE_TOKEN", aliases=("TUSHARE_PRO_TOKEN",)) == "abcdefghijklmnop"

    status = secret_status("TUSHARE_TOKEN", aliases=("TUSHARE_PRO_TOKEN",))
    assert status["status"] == "ok"
    assert status["source"] == "TUSHARE_PRO_TOKEN"
    assert status["masked"] == "abcd****mnop"
    assert "abcdefghijklmnop" not in json.dumps(status)


def test_tushare_token_ignores_yaml_secret_fallback(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "settings.yaml").write_text(
        """
data:
  tushare:
    token: yaml-token-must-not-be-used
project:
  name: test-project
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setenv("ASTROLABE_HOME", str(tmp_path))
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_PRO_TOKEN", raising=False)

    from core.settings import get_settings, get_tushare_token

    assert get_settings(refresh=True)["data"]["tushare"]["token"] == "yaml-token-must-not-be-used"
    assert get_tushare_token() == ""

    monkeypatch.setenv("TUSHARE_TOKEN", "env-token")
    assert get_tushare_token() == "env-token"


def test_llm_provider_key_ignores_env_file_config(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=file-secret-must-not-be-used\n", encoding="utf-8")

    import data.llm.usage as usage

    monkeypatch.setattr(
        usage,
        "get_settings",
        lambda: {
            "llm": {
                "providers": {
                    "deepseek": {
                        "enabled": True,
                        "api_key_env": "DEEPSEEK_API_KEY",
                        "env_file": str(env_file),
                    }
                }
            }
        },
    )
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    assert usage.load_provider_api_key("deepseek") == ""

    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-secret")
    assert usage.load_provider_api_key("deepseek") == "env-secret"


def test_config_env_cli_reports_masked_secret_status(monkeypatch, capsys):
    from astrolabe_cli.main import run_cli

    monkeypatch.setenv("TUSHARE_TOKEN", "abcdefghijklmnop")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret-value")

    code = run_cli(["config", "env", "--json"])
    data = _json_from_cli(capsys)
    rendered = json.dumps(data, ensure_ascii=False)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["missing_count"] == 0
    assert data["data"]["secrets"]["tushare"]["status"] == "ok"
    assert data["data"]["secrets"]["llm.deepseek"]["status"] == "ok"
    assert "abcdefghijklmnop" not in rendered
    assert "deepseek-secret-value" not in rendered
