"""Compatibility shim for `data.features.feature_store`.

Use `data.features.feature_store` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.features.feature_store")
_sys.modules[__name__] = _module
