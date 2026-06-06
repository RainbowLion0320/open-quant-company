"""Compatibility shim for `data.quality.contract`.

Use `data.quality.contract` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.quality.contract")
_sys.modules[__name__] = _module
