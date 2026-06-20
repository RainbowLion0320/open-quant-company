"""Agent-facing CLI control plane for Open Quant Company."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as package_version

__all__ = ["__version__"]


def _resolve_version() -> str:
    try:
        from web.api.version import get_project_version

        project_version = get_project_version()
        if project_version != "0.0.0":
            return project_version
    except Exception:
        pass

    try:
        return package_version("open-quant-company")
    except PackageNotFoundError:
        return "0.0.0"


__version__ = _resolve_version()
