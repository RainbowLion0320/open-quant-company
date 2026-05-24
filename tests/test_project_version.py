import json
import tomllib
from pathlib import Path

import yaml

from web.api import version as version_module


def test_project_meta_prefers_pyproject_version_and_hides_secrets(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "9.8.7"\n',
        encoding="utf-8",
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text(
        yaml.safe_dump(
            {
                "project": {
                    "name": "config-name",
                    "display_name": "星盘测试",
                    "english_name": "Astrolabe Test",
                    "version": "1.2.3",
                    "api_key": "secret",
                    "run_mode": "live",
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(version_module, "ROOT", Path(tmp_path))

    meta = version_module.get_project_meta()

    assert meta["name"] == "config-name"
    assert meta["version"] == "9.8.7"
    assert meta["display_name"] == "星盘测试"
    assert "api_key" not in meta
    assert "run_mode" not in meta


def test_project_version_falls_back_to_settings(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text(
        yaml.safe_dump({"project": {"version": "1.2.3"}}, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setattr(version_module, "ROOT", Path(tmp_path))

    assert version_module.get_project_version() == "1.2.3"


def test_tracked_version_files_are_in_sync():
    root = version_module.ROOT
    with open(root / "pyproject.toml", "rb") as f:
        pyproject_version = (tomllib.load(f).get("project") or {}).get("version")
    with open(root / "config" / "settings.yaml", "r") as f:
        settings_version = ((yaml.safe_load(f) or {}).get("project") or {}).get("version")
    with open(root / "web" / "frontend" / "package.json", "r") as f:
        frontend_version = json.load(f).get("version")

    assert pyproject_version == settings_version == frontend_version
