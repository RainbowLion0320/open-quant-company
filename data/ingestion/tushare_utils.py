"""Shared Tushare configuration helpers."""

from core.settings import get_tushare_token as _get_tushare_token


def get_tushare_token() -> str:
    """Load Tushare token from environment first, then local config fallback."""
    return _get_tushare_token()
