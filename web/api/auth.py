"""
API Authentication — lightweight Bearer token middleware for local single-user.

Reads project.api_key from config/settings.yaml. On first startup, if no
api_key is configured, auto-generates one and writes it back.

Whitelist: /api/health, static /assets, and SPA fallback paths are public.
All other /api/* routes require Authorization: Bearer <key>.

Also provides run_mode guard: research (full), paper (partial), live (read-only).
"""

from __future__ import annotations

import os
import secrets
import yaml
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


# ── Config path resolution ──

def _settings_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"


def _read_settings() -> dict:
    path = _settings_path()
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _write_settings(data: dict):
    path = _settings_path()
    os.makedirs(path.parent, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ── API Key management ──

def get_api_key() -> str:
    """Read API key from config, auto-generate if missing."""
    cfg = _read_settings()
    project = cfg.get("project") or {}
    key = project.get("api_key", "").strip()
    if key:
        return key

    # Auto-generate on first startup
    key = secrets.token_urlsafe(24)
    project["api_key"] = key
    cfg["project"] = project
    _write_settings(cfg)
    return key


def get_run_mode() -> str:
    """Read current run mode: research | paper | live."""
    cfg = _read_settings()
    project = cfg.get("project") or {}
    return project.get("run_mode", "research")


def is_readonly_mode() -> bool:
    """True if current mode restricts settings writes."""
    return get_run_mode() == "live"


# ── Whitelisted paths (no auth required) ──

_PUBLIC_PREFIXES = (
    "/api/health",
    "/assets/",
)

_PUBLIC_EXACT = frozenset({
    "/api/health",
})


def _is_public(path: str) -> bool:
    """Check if the request path does not require auth."""
    if path in _PUBLIC_EXACT:
        return True
    if not path.startswith("/api/"):
        return True  # SPA fallback, favicon, etc.
    return False


# ── Middleware ──

class AuthMiddleware(BaseHTTPMiddleware):
    """Validate Bearer token on all /api/* routes except whitelist."""

    async def dispatch(self, request: Request, call_next):
        if _is_public(request.url.path):
            return await call_next(request)

        token = get_api_key()
        if not token:
            # No API key configured at all — allow all (degraded open mode)
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            provided = auth[7:]
        elif auth:
            provided = auth
        else:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header. Use: Bearer <api_key>"},
            )

        if not secrets.compare_digest(provided, token):
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid API key"},
            )

        return await call_next(request)
