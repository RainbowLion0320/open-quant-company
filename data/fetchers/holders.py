"""Compatibility shim for `data.ingestion.fetchers.holders`.

Use `data.ingestion.fetchers.holders` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ingestion.fetchers.holders")
_sys.modules[__name__] = _module
