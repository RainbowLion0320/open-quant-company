"""Project metadata helpers for API responses."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent.parent
_PUBLIC_PROJECT_KEYS = {"name", "display_name", "english_name", "version", "description"}


def _read_settings_project() -> dict[str, Any]:
    path = ROOT / "config" / "settings.yaml"
    if not path.exists():
        return {}
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    project = data.get("project") or {}
    if not isinstance(project, dict):
        return {}
    return {key: project[key] for key in _PUBLIC_PROJECT_KEYS if key in project}


def _read_pyproject_version() -> str:
    path = ROOT / "pyproject.toml"
    if not path.exists():
        return ""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return str((data.get("project") or {}).get("version") or "").strip()


def get_project_version() -> str:
    """Return canonical project version, preferring pyproject.toml."""
    project = _read_settings_project()
    return _read_pyproject_version() or str(project.get("version") or "").strip() or "0.0.0"


def get_project_meta() -> dict[str, Any]:
    """Return public project metadata without secrets such as API keys."""
    project = _read_settings_project()
    project["version"] = get_project_version()
    project.setdefault("name", "astrolabe-quant")
    project.setdefault("display_name", "星盘")
    project.setdefault("english_name", "Astrolabe Quant OS")
    return project
