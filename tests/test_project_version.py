import re
import tomllib
from pathlib import Path

import yaml

from scripts import bump_version
from web.api import version as version_module


def test_project_meta_uses_pyproject_version_and_hides_config_secrets(tmp_path, monkeypatch):
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


def test_project_version_ignores_settings_version_without_pyproject(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text(
        yaml.safe_dump({"project": {"version": "1.2.3"}}, allow_unicode=True),
        encoding="utf-8",
    )
    monkeypatch.setattr(version_module, "ROOT", Path(tmp_path))

    assert version_module.get_project_version() == "0.0.0"


def test_tracked_version_source_is_pyproject_only():
    root = version_module.ROOT
    with open(root / "pyproject.toml", "rb") as f:
        pyproject_version = (tomllib.load(f).get("project") or {}).get("version")
    with open(root / "config" / "settings.yaml", "r") as f:
        settings_project = (yaml.safe_load(f) or {}).get("project") or {}
    with open(root / "web" / "frontend" / "package.json", "r") as f:
        frontend_package = yaml.safe_load(f) or {}
    with open(root / "web" / "frontend" / "package-lock.json", "r") as f:
        frontend_lock = yaml.safe_load(f) or {}
    readme = (root / "README.md").read_text(encoding="utf-8")
    badge = re.search(r"version-([^-]+)-orange", readme)

    assert pyproject_version == "2.0.0"
    assert "version" not in settings_project
    assert "version" not in frontend_package
    assert "version" not in frontend_lock
    assert "version" not in (frontend_lock.get("packages", {}).get("") or {})
    assert badge and badge.group(1) == pyproject_version


def test_bump_version_updates_canonical_source_and_display_badge(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        '<img src="https://img.shields.io/badge/version-1.0.0-orange" alt="Version">\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(bump_version, "ROOT", Path(tmp_path))

    bump_version.bump("2.1.0")

    with open(tmp_path / "pyproject.toml", "rb") as f:
        assert (tomllib.load(f).get("project") or {}).get("version") == "2.1.0"
    assert "version-2.1.0-orange" in (tmp_path / "README.md").read_text(encoding="utf-8")
