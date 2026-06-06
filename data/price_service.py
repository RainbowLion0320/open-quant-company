"""Compatibility shim for `data.market.price_service`.

Use `data.market.price_service` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.price_service")
_sys.modules[__name__] = _module
