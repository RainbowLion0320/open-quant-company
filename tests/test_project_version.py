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
                    "display_name": "Open Quant Company测试",
                    "english_name": "Open Quant Company Test",
                    "version": "1.2.3",
                    "api_key": "secret",
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
    assert meta["display_name"] == "Open Quant Company测试"
    assert "api_key" not in meta


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
    readme_en = (root / "README.en.md").read_text(encoding="utf-8")
    citation = yaml.safe_load((root / "CITATION.cff").read_text(encoding="utf-8")) or {}
    badge = re.search(r"version-([^-]+)-orange", readme)
    english_badge = re.search(r"version-([^-]+)-orange", readme_en)

    assert pyproject_version == "2026.6.20.1"
    assert re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}\.\d+", pyproject_version)
    assert "version" not in settings_project
    assert "version" not in frontend_package
    assert "version" not in frontend_lock
    assert "version" not in (frontend_lock.get("packages", {}).get("") or {})
    assert badge and badge.group(1) == pyproject_version
    assert english_badge and english_badge.group(1) == pyproject_version
    assert citation.get("version") == pyproject_version
    assert version_module.get_project_version() == pyproject_version


def test_cli_package_version_matches_project_version():
    import astrolabe_cli

    assert astrolabe_cli.__version__ == version_module.get_project_version()


def test_bump_version_updates_canonical_source_and_display_badges(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "2026.6.20.1"\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        '<img src="https://img.shields.io/badge/version-2026.6.20.1-orange" alt="Version">\n',
        encoding="utf-8",
    )
    (tmp_path / "README.en.md").write_text(
        '<img src="https://img.shields.io/badge/version-2026.6.20.1-orange" alt="Version">\n',
        encoding="utf-8",
    )
    (tmp_path / "CITATION.cff").write_text(
        'cff-version: 1.2.0\nversion: "2026.6.20.1"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(bump_version, "ROOT", Path(tmp_path))

    bump_version.bump("2026.6.21.1")

    with open(tmp_path / "pyproject.toml", "rb") as f:
        assert (tomllib.load(f).get("project") or {}).get("version") == "2026.6.21.1"
    assert "version-2026.6.21.1-orange" in (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "version-2026.6.21.1-orange" in (tmp_path / "README.en.md").read_text(encoding="utf-8")
    citation = (tmp_path / "CITATION.cff").read_text(encoding="utf-8")
    assert 'version: "2026.6.21.1"' in citation
    assert 'date-released: "2026-06-21"' in citation
