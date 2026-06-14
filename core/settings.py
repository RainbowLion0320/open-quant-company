"""Central settings loader for Open Quant Company."""

from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, MutableMapping

import yaml

from core.env_secrets import read_env_secret

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_RELATIVE_PATH = Path("config") / "settings.yaml"


def _project_root_from_env() -> Path | None:
    for name in ("ASTROLABE_HOME", "ASTROLABE_ROOT"):
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser().resolve()
    return None


def resolve_settings_path(path: str | os.PathLike | None = None) -> Path:
    """Resolve the canonical settings path, honoring explicit and env overrides."""
    if path:
        return Path(path).expanduser().resolve()

    explicit = os.environ.get("ASTROLABE_SETTINGS")
    if explicit:
        return Path(explicit).expanduser().resolve()

    env_root = _project_root_from_env()
    if env_root:
        return env_root / SETTINGS_RELATIVE_PATH

    repo_path = PROJECT_ROOT / SETTINGS_RELATIVE_PATH
    if repo_path.exists():
        return repo_path

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


def get_dotted(data: Mapping[str, Any], dotted_key: str, default: Any = None) -> Any:
    """Read a dotted key from a nested mapping without treating flat keys as sections."""
    current: Any = data
    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return default
        current = current[part]
    return current


def set_dotted(data: MutableMapping[str, Any], dotted_key: str, value: Any) -> None:
    """Write a dotted key into a nested mutable mapping, creating parents as needed."""
    parts = dotted_key.split(".")
    current: MutableMapping[str, Any] = data
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, MutableMapping):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def get_section(section: str, default: Any = None, *, path: str | os.PathLike | None = None) -> Any:
    """Return a dotted settings section such as ``signals.multifactor``."""
    return copy.deepcopy(get_dotted(get_settings(path), section, default))


def get_tushare_token() -> str:
    """Load Tushare token from process environment only."""
    return read_env_secret("TUSHARE_TOKEN")
