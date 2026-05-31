"""Shared helpers for Web pipeline payload builders."""

from __future__ import annotations

from datetime import datetime

from web.api.serializers import safe_float


def value(regime: object) -> str:
    return regime.value if hasattr(regime, "value") else str(regime or "unknown")


def metric(label: str, value: object, tone: str = "neutral") -> dict[str, object]:
    return {"label": label, "value": value, "tone": tone}


def node(
    node_id: str,
    title: str,
    subtitle: str,
    *,
    status: str = "ready",
    metrics: list[dict[str, object]] | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": node_id,
        "title": title,
        "subtitle": subtitle,
        "status": status,
        "metrics": metrics or [],
        "inputs": inputs or [],
        "outputs": outputs or [],
    }


def edge(source: str, target: str, label: str = "", *, condition: str = "", active: bool = True) -> dict[str, object]:
    result: dict[str, object] = {"source": source, "target": target, "label": label}
    if condition:
        result["condition"] = condition
    if not active:
        result["active"] = False
    return result


def pct(raw: object) -> str:
    return f"{safe_float(raw, 0.0) * 100:.1f}%"


def score(raw: object) -> str:
    return f"{safe_float(raw, 0.0):.1f}"


def updated_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")
