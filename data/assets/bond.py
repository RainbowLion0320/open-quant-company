"""Compatibility shim for `data.market.assets.bond`.

Use `data.market.assets.bond` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.assets.bond")
_sys.modules[__name__] = _module
