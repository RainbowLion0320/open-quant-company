"""Compatibility shim for `data.market.market_data_view`.

Use `data.market.market_data_view` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.market_data_view")
_sys.modules[__name__] = _module
