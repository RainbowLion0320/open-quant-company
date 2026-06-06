"""Compatibility shim for `data.llm.usage`.

Use `data.llm.usage` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.llm.usage")
_sys.modules[__name__] = _module
