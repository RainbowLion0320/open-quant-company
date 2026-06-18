import json
import re
from pathlib import Path

import yaml


def _json_from_cli(capsys):
    return json.loads(capsys.readouterr().out)


def test_env_secret_reader_uses_single_name_and_masks_values(monkeypatch):
    from core.env_secrets import read_env_secret, secret_status

    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setenv("TUSHARE_PRO_TOKEN", "abcdefghijklmnop")

    assert read_env_secret("TUSHARE_TOKEN") == ""

    status = secret_status("TUSHARE_TOKEN")
    assert status["status"] == "missing"

    monkeypatch.setenv("TUSHARE_TOKEN", "abcdefghijklmnop")
    assert read_env_secret("TUSHARE_TOKEN") == "abcdefghijklmnop"

    status = secret_status("TUSHARE_TOKEN")
    assert status["status"] == "ok"
    assert status["source"] == "TUSHARE_TOKEN"
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
    monkeypatch.setenv("MIMO_API_KEY", "mimo-secret-value")

    code = run_cli(["config", "env", "--json"])
    data = _json_from_cli(capsys)
    rendered = json.dumps(data, ensure_ascii=False)

    assert code == 0
    assert data["ok"] is True
    assert data["data"]["missing_count"] == 0
    assert data["data"]["secrets"]["tushare"]["status"] == "ok"
    assert data["data"]["secrets"]["llm.deepseek"]["status"] == "ok"
    assert data["data"]["secrets"]["llm.mimo"]["status"] == "ok"
    assert data["data"]["secrets"]["llm.mimo"]["source"] == "MIMO_API_KEY"
    assert "abcdefghijklmnop" not in rendered
    assert "deepseek-secret-value" not in rendered
    assert "mimo-secret-value" not in rendered


def test_settings_registers_mimo_provider_without_secret_literal():
    text = Path("config/settings.yaml").read_text(encoding="utf-8")
    cfg = yaml.safe_load(text)
    mimo = cfg["llm"]["providers"]["mimo"]

    assert cfg["llm"]["default_provider"] == "mimo"
    assert cfg["llm"]["use_cases"]["agent_planning"] == {"provider": "mimo", "model": "mimo-v2.5-pro"}
    assert cfg["llm"]["use_cases"]["factor_hypothesis"] == {"provider": "mimo", "model": "mimo-v2.5-pro"}
    assert mimo["enabled"] is True
    assert mimo["label"] == "Mimo"
    assert mimo["protocol"] == "openai_compatible"
    assert mimo["api_key_env"] == "MIMO_API_KEY"
    assert mimo["base_url"] == "https://token-plan-cn.xiaomimimo.com/v1"
    assert mimo["default_model"] == "mimo-v2.5-pro"
    assert "token-plan-cn.xiaomimimo.com" in text
    assert re.search(r"\btp-[a-z0-9]{20,}\b", text) is None


def test_config_env_cli_reports_custom_llm_provider_secret(monkeypatch, capsys):
    import data.llm.usage as usage
    from astrolabe_cli.main import run_cli

    monkeypatch.setenv("TUSHARE_TOKEN", "abcdefghijklmnop")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret-value")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dashscope-secret-value")
    monkeypatch.setattr(
        usage,
        "get_settings",
        lambda: {
            "llm": {
                "providers": {
                    "qwen": {
                        "enabled": True,
                        "api_key_env": "DASHSCOPE_API_KEY",
                    }
                }
            }
        },
    )

    code = run_cli(["config", "env", "--json"])
    data = _json_from_cli(capsys)
    rendered = json.dumps(data, ensure_ascii=False)

    assert code == 0
    assert data["data"]["secrets"]["llm.qwen"]["status"] == "ok"
    assert data["data"]["secrets"]["llm.qwen"]["source"] == "DASHSCOPE_API_KEY"
    assert "dashscope-secret-value" not in rendered


def test_config_validate_rejects_invalid_llm_provider_configuration(monkeypatch):
    import astrolabe_cli.commands.config as config_cmd
    import core.settings as settings
    import data.strategy.catalog as catalog

    monkeypatch.setattr(catalog, "load_registry", lambda force_reload=False: {})
    monkeypatch.setattr(catalog, "get_enabled_strategies", lambda: [])
    monkeypatch.setattr(
        settings,
        "get_settings",
        lambda: {
            "strategies": {},
            "backtest": {},
            "risk_control": {},
            "llm": {
                "default_provider": "qwen",
                "use_cases": {
                    "agent_planning": {"provider": "missing-provider", "model": "x"},
                    "factor_hypothesis": {"provider": "qwen", "model": "qwen-plus"},
                },
                "providers": {
                    "qwen": {
                        "enabled": True,
                        "protocol": "native_sdk",
                        "api_key_env": "DASHSCOPE_API_KEY",
                        "base_url": "",
                        "default_model": "",
                    }
                },
            },
        },
    )

    result = config_cmd.validate_config()

    assert result.ok is False
    assert "llm.use_cases.agent_planning.provider unknown: missing-provider" in result.errors
    assert "llm.providers.qwen.protocol unsupported: native_sdk" in result.errors
    assert "llm.providers.qwen.base_url missing" in result.errors
    assert "llm.providers.qwen.default_model missing" in result.errors
