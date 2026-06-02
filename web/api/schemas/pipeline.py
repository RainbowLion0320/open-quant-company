"""Pipeline response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class PipelineNode(BaseModel):
    id: str = ""
    title: str = ""
    subtitle: str = ""
    status: str = ""
    kind: str = "stage"
    metrics: list[Any] = []
    inputs: list[Any] = []
    outputs: list[Any] = []


class PipelineEdge(BaseModel):
    source: str = ""
    target: str = ""
    label: str = ""
    condition: str = ""
    active: bool = True


class PipelineDetailResponse(BaseModel):
    pipeline_key: str = ""
    updated: str = ""
    summary: dict[str, Any] = {}
    nodes: list[PipelineNode] = []
    edges: list[PipelineEdge] = []
    warnings: list[str] = []


class PipelineRegistryItem(BaseModel):
    key: str = ""
    label: str = ""
    status: str = "available"


class PipelineRegistryResponse(BaseModel):
    items: list[PipelineRegistryItem] = []
    total: int = 0
