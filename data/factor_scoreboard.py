"""Compatibility shim for `data.features.factor_scoreboard`.

Use `data.features.factor_scoreboard` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.features.factor_scoreboard")
_sys.modules[__name__] = _module
