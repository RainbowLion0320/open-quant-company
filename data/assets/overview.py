"""Compatibility shim for `data.market.assets.overview`.

Use `data.market.assets.overview` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.assets.overview")
_sys.modules[__name__] = _module
