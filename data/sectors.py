"""Compatibility shim for `data.market.sectors`.

Use `data.market.sectors` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.sectors")
_sys.modules[__name__] = _module
