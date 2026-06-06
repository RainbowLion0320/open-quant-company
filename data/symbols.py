"""Compatibility shim for `data.market.symbols`.

Use `data.market.symbols` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.symbols")
_sys.modules[__name__] = _module
