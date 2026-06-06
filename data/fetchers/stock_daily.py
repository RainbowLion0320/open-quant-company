"""Compatibility shim for `data.ingestion.fetchers.stock_daily`.

Use `data.ingestion.fetchers.stock_daily` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ingestion.fetchers.stock_daily")
_sys.modules[__name__] = _module
