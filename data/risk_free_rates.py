"""Compatibility shim for `data.rates.risk_free_rates`.

Use `data.rates.risk_free_rates` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.rates.risk_free_rates")
_sys.modules[__name__] = _module
