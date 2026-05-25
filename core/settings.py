"""Central settings loader for the Astrolabe Quant project."""

from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_RELATIVE_PATH = Path("config") / "settings.yaml"


def _project_root_from_env() -> Path | None:
    for name in ("ASTROLABE_HOME", "ASTROLABE_ROOT", "XINGPAN_HOME", "QUANT_AGENT_HOME"):
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser().resolve()
    return None


def resolve_settings_path(path: str | os.PathLike | None = None) -> Path:
    """Resolve the canonical settings path, honoring explicit and env overrides."""
    if path:
        return Path(path).expanduser().resolve()

    explicit = os.environ.get("ASTROLABE_SETTINGS") or os.environ.get("QUANT_AGENT_SETTINGS")
    if explicit:
        return Path(explicit).expanduser().resolve()

    env_root = _project_root_from_env()
    if env_root:
        return env_root / SETTINGS_RELATIVE_PATH

    repo_path = PROJECT_ROOT / SETTINGS_RELATIVE_PATH
    if repo_path.exists():
        return repo_path

    for legacy in ("~/astrolabe-quant", "~/quant-agent", "~/xingpan"):
        candidate = Path(legacy).expanduser() / SETTINGS_RELATIVE_PATH
        if candidate.exists():
            return candidate.resolve()

    return repo_path


def load_yaml_config(path: str | os.PathLike, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Load a YAML mapping; return a defensive default when the file is absent or invalid."""
    try:
        with open(Path(path).expanduser(), encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else copy.deepcopy(default or {})
    except Exception:
        return copy.deepcopy(default or {})


@lru_cache(maxsize=8)
def _cached_settings(path_text: str) -> dict[str, Any]:
    return load_yaml_config(path_text, default={})


def get_settings(path: str | os.PathLike | None = None, *, refresh: bool = False) -> dict[str, Any]:
    """Return a deep copy of project settings so callers cannot mutate the cache."""
    resolved = resolve_settings_path(path)
    if refresh:
        _cached_settings.cache_clear()
    return copy.deepcopy(_cached_settings(str(resolved)))


def clear_settings_cache() -> None:
    """Invalidate cached settings after config writes."""
    _cached_settings.cache_clear()


def get_section(section: str, default: Any = None, *, path: str | os.PathLike | None = None) -> Any:
    """Return a dotted settings section such as ``signals.multifactor``."""
    current: Any = get_settings(path)
    for part in section.split("."):
        if not isinstance(current, dict) or part not in current:
            return copy.deepcopy(default)
        current = current[part]
    return copy.deepcopy(current)


def get_tushare_token() -> str:
    """Load Tushare token from environment first, then settings fallback."""
    token = os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_PRO_TOKEN")
    if token:
        return token.strip()

    token = str(get_section("data.tushare.token", "") or "").strip()
    if token.startswith("${") and token.endswith("}"):
        return ""
    return token
