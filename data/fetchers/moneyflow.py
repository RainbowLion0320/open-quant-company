"""Compatibility shim for `data.ingestion.fetchers.moneyflow`.

Use `data.ingestion.fetchers.moneyflow` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ingestion.fetchers.moneyflow")
_sys.modules[__name__] = _module
