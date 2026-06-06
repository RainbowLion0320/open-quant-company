"""Compatibility shim for `data.market.assets.etf`.

Use `data.market.assets.etf` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.assets.etf")
_sys.modules[__name__] = _module
