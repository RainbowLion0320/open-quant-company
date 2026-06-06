"""Compatibility shim for `data.quality.freshness_gate`.

Use `data.quality.freshness_gate` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.quality.freshness_gate")
_sys.modules[__name__] = _module
