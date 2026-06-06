"""Compatibility shim for `data.market.sector_pipeline.exposure`.

Use `data.market.sector_pipeline.exposure` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.market.sector_pipeline.exposure")
_sys.modules[__name__] = _module
