"""Compatibility shim for `data.market.assets.base`.

Use `data.market.assets.base` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.assets.base")
_sys.modules[__name__] = _module
