from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from agent_os.tools import DEFAULT_TOOLS
from data.llm.usage import load_provider_api_key
from data.llm.usage import record_llm_response_usage
from data.llm.usage import resolve_llm_use_case


class SemanticDraftPlanner:
    """Adapter for externally drafted semantic plans.

    The draft is treated as untrusted input. It is only a planner-shaped object;
    `agent_os.workflows` still applies the fixed-registry tool, desk-scope, and
    risk-level filters before any action is previewed or proposed.
    """

    def __init__(self, draft: dict[str, Any]):
        self._draft = dict(draft)

    def plan(
        self,
        *,
        desk: str,
        content: str,
        artifact_context: dict[str, Any],
        session_context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            **self._draft,
            "source": "semantic_draft",
            "request_context": {
                "desk": desk,
                "content_length": len(content),
                "artifact_context_seen": bool(artifact_context),
                "session_context_seen": bool(session_context),
            },
        }


class ProviderSemanticPlanner:
    """OpenAI-compatible semantic planning adapter.

    This is an opt-in draft producer, not an executor. It can call a configured
    LLM provider only when the provider has an env-only API key. The returned
    draft is still filtered by `agent_os.workflows` before any action appears in
    a preview or ledger row.
    """

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        transport: Any | None = None,
        timeout_seconds: float = 20.0,
    ):
        self._provider = provider
        self._model = model
        self._transport = transport or _openai_compatible_chat_completion
        self._timeout_seconds = float(timeout_seconds)

    def plan(
        self,
        *,
        desk: str,
        content: str,
        artifact_context: dict[str, Any],
        session_context: dict[str, Any],
    ) -> dict[str, Any]:
        runtime = resolve_llm_use_case("agent_planning", provider=self._provider, model=self._model)
        provider = runtime["provider"]
        model = runtime["model"]
        provider_reasoning = {
            "kind": "semantic_provider",
            "provider": provider,
            "model": model,
            "credential_env": runtime["credential_env"],
        }
        if runtime.get("block_reason") == "provider_not_configured":
            return _provider_blocked_draft(
                "semantic_provider_not_configured",
                "Semantic provider is not configured; no provider request was sent.",
                {**provider_reasoning, "status": "not_configured"},
            )
        if runtime.get("block_reason") == "provider_disabled" or not runtime.get("enabled", True):
            return _provider_blocked_draft(
                "semantic_provider_disabled",
                "Semantic provider is disabled in configuration; no provider request was sent.",
                {**provider_reasoning, "status": "disabled"},
            )
        if runtime.get("block_reason") == "unsupported_protocol":
            return _provider_blocked_draft(
                "semantic_provider_unsupported_protocol",
                "Semantic provider protocol is unsupported; no provider request was sent.",
                {**provider_reasoning, "status": "unsupported_protocol", "protocol": runtime.get("protocol", "")},
            )
        key = load_provider_api_key(provider)
        if not key:
            return _provider_blocked_draft(
                "semantic_provider_missing_secret",
                "Semantic provider API key is missing; no provider request was sent.",
                {**provider_reasoning, "status": "missing_secret"},
            )
        if runtime.get("block_reason") == "base_url_missing" or not runtime["base_url"]:
            return _provider_blocked_draft(
                "semantic_provider_base_url_missing",
                "Semantic provider base_url is missing; no provider request was sent.",
                {**provider_reasoning, "status": "missing_base_url"},
            )
        if runtime.get("block_reason") == "model_missing" or not model:
            return _provider_blocked_draft(
                "semantic_provider_model_missing",
                "Semantic provider model is missing; no provider request was sent.",
                {**provider_reasoning, "status": "missing_model"},
            )

        request = {
            "use_case": "agent_planning",
            "provider": provider,
            "model": model,
            "base_url": runtime["base_url"],
            "chat_path": runtime.get("chat_path", "/chat/completions"),
            "response_format_json": bool(runtime.get("response_format_json", True)),
            "temperature": float(runtime.get("temperature", 0.1) or 0.1),
            "api_key": key,
            "timeout_seconds": float(runtime.get("timeout_seconds", self._timeout_seconds) or self._timeout_seconds),
            "messages": _semantic_provider_messages(
                desk=desk,
                content=content,
                artifact_context=artifact_context,
                session_context=session_context,
            ),
            "allowed_tools": _safe_tool_contracts(),
        }
        try:
            response = self._transport(request)
            draft = _draft_from_provider_response(response)
        except Exception as exc:
            return _provider_blocked_draft(
                "semantic_provider_error",
                "Semantic provider request failed; no provider draft was accepted.",
                {
                    **provider_reasoning,
                    "status": "error",
                    "error_class": type(exc).__name__,
                },
            )
        usage_record = _record_provider_usage(response, provider=provider, model=model)
        draft_reasoning = [row for row in draft.get("reasoning", []) if isinstance(row, dict)]
        draft["reasoning"] = [
            {
                **provider_reasoning,
                "status": "ok",
                "usage": _provider_usage(response),
                "usage_recorded": bool(usage_record.get("recorded")),
                **({"usage_error_class": usage_record["error_class"]} if usage_record.get("error_class") else {}),
            },
            *draft_reasoning,
        ]
        return draft


def semantic_planner_from_payload(payload: dict[str, Any]) -> SemanticDraftPlanner | ProviderSemanticPlanner | None:
    mode = str(payload.get("planner_mode") or "deterministic").strip()
    if mode in {"", "deterministic", "fixed_registry"}:
        return None
    if mode == "semantic_draft":
        draft = payload.get("semantic_draft")
        if not isinstance(draft, dict):
            raise ValueError("planner_mode=semantic_draft requires semantic_draft object")
        return SemanticDraftPlanner(draft)
    if mode == "provider_semantic":
        return ProviderSemanticPlanner(
            provider=str(payload.get("planner_provider") or "") or None,
            model=str(payload.get("planner_model") or "") or None,
        )
    raise ValueError(f"Unsupported planner_mode: {mode}")


def semantic_planner_from_file(path: str | Path | None) -> SemanticDraftPlanner | None:
    if path is None or str(path).strip() == "":
        return None
    draft_path = Path(path).expanduser()
    try:
        raw = json.loads(draft_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Semantic draft file not found: {draft_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Semantic draft file is not valid JSON: {draft_path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Semantic draft file must contain a JSON object")
    return SemanticDraftPlanner(raw)


def semantic_planner_from_cli(
    *,
    semantic_draft_file: str = "",
    provider_semantic: bool = False,
    planner_provider: str = "",
    planner_model: str = "",
) -> SemanticDraftPlanner | ProviderSemanticPlanner | None:
    if semantic_draft_file and provider_semantic:
        raise ValueError("--semantic-draft-file and --provider-semantic are mutually exclusive")
    if semantic_draft_file:
        return semantic_planner_from_file(semantic_draft_file)
    if provider_semantic:
        return ProviderSemanticPlanner(
            provider=planner_provider or None,
            model=planner_model or None,
        )
    return None


def _provider_blocked_draft(blocker: str, answer: str, reasoning: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": answer,
        "confidence": 0.0,
        "actions": [],
        "reasoning": [reasoning],
        "blockers": [blocker],
    }


def _safe_tool_contracts() -> list[dict[str, Any]]:
    rows = []
    for tool in DEFAULT_TOOLS.values():
        if tool.risk_level not in {"read_only", "dry_run"}:
            continue
        rows.append(
            {
                "tool_id": tool.tool_id,
                "label": tool.label,
                "risk_level": tool.risk_level,
                "desk_scopes": list(tool.desk_scopes),
            }
        )
    return rows


def _semantic_provider_messages(
    *,
    desk: str,
    content: str,
    artifact_context: dict[str, Any],
    session_context: dict[str, Any],
) -> list[dict[str, str]]:
    safe_context = {
        "desk": desk,
        "content": content,
        "artifact_context": _redact_provider_context(artifact_context),
        "session_context": _redact_provider_context(session_context),
        "allowed_tools": _safe_tool_contracts(),
    }
    return [
        {
            "role": "system",
            "content": (
                "You are the semantic planning desk for Open Quant Company. "
                "Return only a JSON object with answer, confidence, actions, reasoning, and blockers. "
                "Actions must use only allowed_tools, must be read_only or dry_run, and must not trade, "
                "write data, write code, or invent tool ids."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(safe_context, ensure_ascii=False, sort_keys=True),
        },
    ]


def _redact_provider_context(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_like_key(key_text):
                redacted[key_text] = "***REDACTED***"
            else:
                redacted[key_text] = _redact_provider_context(item)
        return redacted
    if isinstance(value, list):
        return [_redact_provider_context(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_provider_context(item) for item in value]
    return value


def _is_secret_like_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    secret_tokens = ("secret", "token", "password", "api_key", "apikey", "authorization", "credential")
    return any(token in normalized for token in secret_tokens)


def _openai_compatible_chat_completion(request: dict[str, Any]) -> dict[str, Any]:
    base_url = str(request.get("base_url") or "").rstrip("/")
    chat_path = str(request.get("chat_path") or "/chat/completions")
    if not chat_path.startswith("/"):
        chat_path = f"/{chat_path}"
    url = f"{base_url}{chat_path}"
    payload = {
        "model": str(request.get("model") or ""),
        "messages": request.get("messages") or [],
        "temperature": float(request.get("temperature", 0.1) or 0.1),
    }
    if bool(request.get("response_format_json", True)):
        payload["response_format"] = {"type": "json_object"}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {request.get('api_key')}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=float(request.get("timeout_seconds") or 20.0)) as response:
        return json.loads(response.read().decode("utf-8"))


def _draft_from_provider_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise ValueError("provider response must be an object")
    content = _provider_message_content(response)
    if isinstance(content, dict):
        draft = content
    else:
        draft = _parse_json_object(str(content or ""))
    if not isinstance(draft, dict):
        raise ValueError("provider message content must contain a JSON object")
    return {
        "answer": str(draft.get("answer") or ""),
        "confidence": float(draft.get("confidence") or 0.5),
        "actions": [dict(row) for row in draft.get("actions", []) if isinstance(row, dict)],
        "reasoning": [dict(row) for row in draft.get("reasoning", []) if isinstance(row, dict)],
        "blockers": [str(row) for row in draft.get("blockers", []) if str(row).strip()],
    }


def _provider_message_content(response: dict[str, Any]) -> Any:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("provider response missing choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("provider choice must be an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ValueError("provider choice missing message")
    return message.get("content")


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return json.loads(cleaned)


def _provider_usage(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {}
    return {str(key): value for key, value in usage.items() if isinstance(value, int | float | str)}


def _record_provider_usage(response: Any, *, provider: str, model: str) -> dict[str, Any]:
    try:
        row = record_llm_response_usage(response, provider=provider, model=model, source="agent_planning")
    except Exception as exc:
        return {"recorded": False, "error_class": type(exc).__name__}
    return {"recorded": bool(row), "error_class": ""}
