"""Compatibility shim for `data.market.assets.crypto`.

Use `data.market.assets.crypto` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.assets.crypto")
_sys.modules[__name__] = _module
