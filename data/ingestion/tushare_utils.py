"""Shared Tushare configuration helpers."""

from core.settings import get_tushare_token as _get_tushare_token


def get_tushare_token() -> str:
    """Load the Tushare token from the process environment."""
    return _get_tushare_token()
