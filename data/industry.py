"""Compatibility shim for `data.market.industry`.

Use `data.market.industry` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.industry")
_sys.modules[__name__] = _module
