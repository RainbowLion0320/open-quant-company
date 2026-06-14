"""Deterministic external source discovery helpers."""

from __future__ import annotations

import json
import urllib.request
from typing import Any

DISCOVERY_DEPTHS = {"catalog", "sample"}
BACKEND_SOURCE_SUFFIXES = {
    "_tx": "tencent_finance",
    "_em": "eastmoney",
    "_sina": "sina_finance",
    "_ths": "tonghuashun",
}
BACKEND_SOURCE_IDS = set(BACKEND_SOURCE_SUFFIXES.values())
SAMPLE_PROBE_ALLOWLIST = {
    ("tencent_finance", "qt_gtimg_realtime_quote"),
    ("tencent_finance", "ifzq_fqkline"),
}


def backend_source_for_akshare_name(name: str) -> str:
    lowered = name.lower()
    for suffix, source in BACKEND_SOURCE_SUFFIXES.items():
        if lowered.endswith(suffix) or f"{suffix}_" in lowered:
            return source
    return ""


def probe_candidate_capability_sample(capability: dict[str, Any]) -> dict[str, Any] | None:
    source = str(capability.get("source", ""))
    interface = str(capability.get("interface", ""))
    if (source, interface) not in SAMPLE_PROBE_ALLOWLIST:
        return None
    try:
        if source == "tencent_finance" and interface == "qt_gtimg_realtime_quote":
            from data.ingestion.tencent_finance import parse_realtime_quote

            with urllib.request.urlopen("https://qt.gtimg.cn/q=sh600519", timeout=6) as response:
                text = response.read().decode("gbk", errors="replace")
            parsed = parse_realtime_quote(text)
            return {
                "status": "ok",
                "row_count": 1,
                "field_sample": sorted(parsed.keys()),
                "message": "sample parsed",
            }
        if source == "tencent_finance" and interface == "ifzq_fqkline":
            from data.ingestion.tencent_finance import parse_fqkline_payload

            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,2,qfq"
            with urllib.request.urlopen(url, timeout=6) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace"))
            rows = parse_fqkline_payload(payload, symbol="sh600519", adjust="qfq")
            return {
                "status": "ok",
                "row_count": len(rows),
                "field_sample": sorted(rows[0].keys()) if rows else [],
                "message": "sample parsed",
            }
    except Exception as exc:
        return {"status": "error", "row_count": 0, "field_sample": [], "message": str(exc)[:240]}
    return None
