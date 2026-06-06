"""Compatibility shim for `data.storage.db`.

Use `data.storage.db` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.storage.db")
_sys.modules[__name__] = _module
