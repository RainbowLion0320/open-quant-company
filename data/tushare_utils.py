"""Shared Tushare configuration helpers."""
import os
from pathlib import Path
from typing import Any

import yaml


def get_tushare_token() -> str:
    """Load Tushare token from environment first, then local config fallback."""
    token = os.environ.get("TUSHARE_TOKEN") or os.environ.get("TUSHARE_PRO_TOKEN")
    if token:
        return token.strip()

    cfg_path = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    try:
        with open(cfg_path) as f:
            cfg: dict[str, Any] = yaml.safe_load(f) or {}
    except Exception:
        return ""

    token = str(cfg.get("data", {}).get("tushare", {}).get("token", "") or "").strip()
    if token.startswith("${") and token.endswith("}"):
        return ""
    return token
