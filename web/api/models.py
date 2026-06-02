"""Compatibility re-export for domain-split API schemas.

New code should import from ``web.api.schemas`` or one of its domain modules.
Existing route modules can continue importing from ``web.api.models``.
"""

from web.api.schemas import *  # noqa: F401,F403
