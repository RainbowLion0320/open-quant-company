"""Compatibility shim for `data.market.assets.stock`.

Use `data.market.assets.stock` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.assets.stock")
_sys.modules[__name__] = _module
