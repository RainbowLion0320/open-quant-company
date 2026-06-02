"""System and common response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from web.api.version import get_project_version


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    timestamp: str = ""


class HealthResponse(BaseModel):
    status: str = "ok"
    backend: str = "duckdb"
    data_updated: str = ""
    stocks_scanned: int = 0
    strategies: int = 0


class SystemHealthItem(BaseModel):
    name: str = ""
    status: str = ""
    detail: str = ""


class SystemHealthResponse(BaseModel):
    items: list[SystemHealthItem] = []
    summary: str = ""
    all_ok: bool = True


class CronJobItem(BaseModel):
    name: str = ""
    schedule: str = ""
    last_run: str = ""
    last_status: str = ""
    next_run: str = ""
    enabled: bool = True
    state: str = ""
    no_agent: bool = False


class CronJobsResponse(BaseModel):
    jobs: list[CronJobItem] = []
    summary: str = ""
    checked_at: str = ""
    version: str = Field(default_factory=get_project_version)
