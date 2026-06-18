"""
API Authentication — lightweight Bearer token middleware for local single-user.

Reads the API key from ``ASTROLABE_API_KEY``. If none is configured, auth is
disabled so the local dashboard keeps working in the default single-user setup.

Whitelist: /api/health, static /assets, and SPA fallback paths are public.
All other /api/* routes require Authorization: Bearer <key> when a key exists.

"""

from __future__ import annotations

import os
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


# ── API Key management ──

def get_api_key() -> str:
    """Read API key from the process environment only."""
    return os.environ.get("ASTROLABE_API_KEY", "").strip()


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
        if request.method == "OPTIONS":
            return await call_next(request)

        if _is_public(request.url.path):
            return await call_next(request)

        token = get_api_key()
        if not token:
            # No API key configured: local requests are accepted without auth.
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            provided = auth[7:]
        elif auth:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid Authorization header. Use: Bearer <token>"},
            )
        else:
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing Authorization header. Use: Bearer <token>"},
            )

        if not secrets.compare_digest(provided, token):
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid API key"},
            )

        return await call_next(request)
