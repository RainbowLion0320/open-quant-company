"""Compatibility shim for `data.market.sector_pipeline.signals`.

Use `data.market.sector_pipeline.signals` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.sector_pipeline.signals")
_sys.modules[__name__] = _module
