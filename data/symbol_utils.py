"""Compatibility shim for `data.market.symbol_utils`.

Use `data.market.symbol_utils` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.symbol_utils")
_sys.modules[__name__] = _module
