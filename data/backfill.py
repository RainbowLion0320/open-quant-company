"""Compatibility shim for `data.ops.backfill`.

Use `data.ops.backfill` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ops.backfill")
_sys.modules[__name__] = _module
