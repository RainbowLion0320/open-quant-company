"""Compatibility shim for `data.ingestion.provider`.

Use `data.ingestion.provider` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ingestion.provider")
_sys.modules[__name__] = _module
