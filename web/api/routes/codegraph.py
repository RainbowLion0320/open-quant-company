"""CodeGraph visualization API."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from web.api.services.codegraph import CodeGraphService, run_codegraph_sync
from web.api.services.codegraph_diagnostics import CodeGraphDiagnosticsService

router = APIRouter(prefix="/api/codegraph", tags=["CodeGraph"])
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class CodeGraphSyncRequest(BaseModel):
    mode: Literal["sync", "rebuild"] = "sync"


def _service() -> CodeGraphService:
    return CodeGraphService(PROJECT_ROOT)


def _diagnostics_service() -> CodeGraphDiagnosticsService:
    return CodeGraphDiagnosticsService(PROJECT_ROOT)


def _csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


@router.get("/status")
async def codegraph_status():
    return _service().status()


@router.get("/graph")
async def codegraph_graph(
    level: Literal["module", "file", "symbol"] = "module",
    root: str = "",
    edge_kinds: str | None = Query(default=None),
    node_kinds: str | None = Query(default=None),
    limit: int = 300,
):
    try:
        return _service().graph(
            level=level,
            root=root,
            edge_kinds=_csv(edge_kinds),
            node_kinds=_csv(node_kinds),
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/search")
async def codegraph_search(q: str = "", limit: int = 20):
    return {"items": _service().search(q, limit=limit)}


@router.get("/neighborhood")
async def codegraph_neighborhood(node_id: str, depth: int = 1, limit: int = 180):
    return _service().neighborhood(node_id, depth=depth, limit=limit)


@router.get("/diagnostics")
async def codegraph_diagnostics(
    scope: Literal["summary", "module", "file", "symbol"] = "summary",
    root: str = "",
    limit: int = 80,
    include_git: bool = True,
):
    return _diagnostics_service().diagnostics(scope=scope, root=root, limit=limit, include_git=include_git)


@router.post("/sync")
async def codegraph_sync(request: CodeGraphSyncRequest):
    result = run_codegraph_sync(PROJECT_ROOT, request.mode)
    if result["status"] == "conflict":
        raise HTTPException(status_code=409, detail=result["message"])
    if result["status"] == "failed":
        raise HTTPException(status_code=500, detail=result)
    return result
