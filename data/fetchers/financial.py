"""Compatibility shim for `data.ingestion.fetchers.financial`.

Use `data.ingestion.fetchers.financial` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ingestion.fetchers.financial")
_sys.modules[__name__] = _module
