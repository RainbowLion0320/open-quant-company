"""Compatibility shim for `data.ingestion.fetcher`.

Use `data.ingestion.fetcher` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ingestion.fetcher")
_sys.modules[__name__] = _module
