"""Read-only Data Source Capability artifact payloads."""

from __future__ import annotations

from typing import Any

from data.ingestion.source_capabilities import sources_summary_payload


def data_source_capabilities_payload() -> dict[str, Any]:
    return sources_summary_payload()
