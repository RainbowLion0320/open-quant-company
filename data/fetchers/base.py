"""Compatibility shim for `data.ingestion.fetchers.base`.

Use `data.ingestion.fetchers.base` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ingestion.fetchers.base")
_sys.modules[__name__] = _module
