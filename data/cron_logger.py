"""Compatibility shim for `data.ops.cron_logger`.

Use `data.ops.cron_logger` for new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_module = _import_module("data.ops.cron_logger")
_sys.modules[__name__] = _module
