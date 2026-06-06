"""Compatibility wrappers for the generic LLM usage ledger."""

from __future__ import annotations

from typing import Any

from data.llm.usage import (
    append_llm_usage,
    fetch_provider_balance,
    load_provider_api_key,
    normalize_llm_usage,
    record_llm_response_usage,
    summarize_llm_project_usage,
)


def load_deepseek_api_key() -> str:
    return load_provider_api_key("deepseek")


def fetch_deepseek_balance(api_key: str | None = None, *, timeout: float = 5.0) -> dict[str, Any]:
    return fetch_provider_balance("deepseek", api_key=api_key, timeout=timeout)


def normalize_deepseek_usage(model: str, usage: Any, **kwargs) -> dict[str, Any]:
    return normalize_llm_usage("deepseek", model, usage, **kwargs)


def append_deepseek_usage(model: str, usage: Any, **kwargs) -> dict[str, Any]:
    return append_llm_usage("deepseek", model, usage, **kwargs)


def record_deepseek_response_usage(response: Any, *, model: str, source: str, request_id: str = "") -> dict[str, Any] | None:
    return record_llm_response_usage(response, provider="deepseek", model=model, source=source, request_id=request_id)


def summarize_deepseek_project_usage(days: int = 30) -> dict[str, Any]:
    return summarize_llm_project_usage(days=days, provider="deepseek")
