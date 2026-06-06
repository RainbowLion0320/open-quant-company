"""Compatibility shim for `data.market.price_types`.

Use `data.market.price_types` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.price_types")
_sys.modules[__name__] = _module
