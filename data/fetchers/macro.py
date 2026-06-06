"""Compatibility shim for `data.ingestion.fetchers.macro`.

Use `data.ingestion.fetchers.macro` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ingestion.fetchers.macro")
_sys.modules[__name__] = _module
