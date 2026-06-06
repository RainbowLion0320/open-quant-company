"""Compatibility shim for `data.ops.audit`.

Use `data.ops.audit` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ops.audit")
_sys.modules[__name__] = _module
