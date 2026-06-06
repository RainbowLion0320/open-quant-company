"""Compatibility shim for `data.storage.datahub_dimensions`.

Use `data.storage.datahub_dimensions` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.storage.datahub_dimensions")
_sys.modules[__name__] = _module
