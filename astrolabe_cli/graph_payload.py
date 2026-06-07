from __future__ import annotations

from collections import Counter
from typing import Any


class GraphPayloadBuilder:
    """Small builder for artifact graph payloads with counted nodes and links."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._links: Counter[tuple[str, str, str]] = Counter()

    def add_node(
        self,
        node_id: str,
        label: str,
        kind: str,
        group: str,
        path: str = "",
        *,
        count: int = 1,
    ) -> None:
        if node_id not in self._nodes:
            self._nodes[node_id] = {
                "id": node_id,
                "label": label,
                "kind": kind,
                "group": group,
                "path": path,
                "count": 0,
            }
        self._nodes[node_id]["count"] += count

    def add_link(self, source: str, target: str, kind: str) -> None:
        self._links[(source, target, kind)] += 1

    def payload(self) -> dict[str, Any]:
        return {
            "nodes": sorted(self._nodes.values(), key=lambda item: (item["kind"], item["id"])),
            "links": [
                {"source": source, "target": target, "type": kind, "label": kind, "count": count}
                for (source, target, kind), count in sorted(self._links.items())
            ],
        }
