from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agent_os.llm_transport import openai_compatible_chat_completion
from agent_os.llm_transport import parse_json_object
from agent_os.llm_transport import provider_message_content
from agent_os.llm_transport import provider_usage
from data.llm.usage import load_provider_api_key
from data.llm.usage import record_llm_response_usage
from data.llm.usage import resolve_llm_use_case


AGENT_RESPONSE_USE_CASE = "agent_response"
_openai_compatible_chat_completion = openai_compatible_chat_completion


@dataclass(frozen=True)
class AgentResponseSynthesis:
    answer: str
    ok: bool
    provider: str
    model: str
    blockers: list[str]
    reasoning: dict[str, Any]


def synthesize_agent_response(
    *,
    desk: str,
    ceo_message: str,
    plan_context: dict[str, Any],
    session_context: dict[str, Any],
    evidence_refs: list[str] | None = None,
    action_refs: list[str] | None = None,
    run_context: dict[str, Any] | None = None,
    phase: str = "initial_response",
    transport: Any | None = None,
) -> AgentResponseSynthesis:
    runtime = resolve_llm_use_case(AGENT_RESPONSE_USE_CASE)
    provider = str(runtime.get("provider") or "")
    model = str(runtime.get("model") or "")
    context_pack = session_context.get("context_pack") if isinstance(session_context.get("context_pack"), dict) else {}
    context_artifact = context_pack.get("artifact") if isinstance(context_pack.get("artifact"), dict) else {}
    base_reasoning = {
        "kind": "agent_response",
        "use_case": AGENT_RESPONSE_USE_CASE,
        "phase": phase,
        "provider": provider,
        "model": model,
        "credential_env": str(runtime.get("credential_env") or ""),
        "context_status": str(context_pack.get("status") or "unknown"),
        "context_mode": str(context_pack.get("mode") or ""),
        "context_artifact": str(context_artifact.get("path") or ""),
    }

    blocked = _runtime_blocker(runtime, provider=provider, context_pack=context_pack)
    if blocked:
        return _blocked_response(provider=provider, model=model, blocker=blocked, reasoning=base_reasoning)

    key = load_provider_api_key(provider)
    if not key:
        return _blocked_response(
            provider=provider,
            model=model,
            blocker="agent_response_missing_secret",
            reasoning={**base_reasoning, "status": "missing_secret"},
        )

    request = {
        "use_case": AGENT_RESPONSE_USE_CASE,
        "provider": provider,
        "model": model,
        "base_url": str(runtime.get("base_url") or ""),
        "chat_path": str(runtime.get("chat_path") or "/chat/completions"),
        "response_format_json": bool(runtime.get("response_format_json", True)),
        "temperature": float(runtime.get("temperature", 0.2) or 0.2),
        "extra_body": runtime.get("extra_body") if isinstance(runtime.get("extra_body"), dict) else {},
        "api_key": key,
        "timeout_seconds": float(runtime.get("timeout_seconds", 20.0) or 20.0),
        "messages": _response_messages(
            desk=desk,
            ceo_message=ceo_message,
            plan_context=plan_context,
            session_context=session_context,
            evidence_refs=list(evidence_refs or []),
            action_refs=list(action_refs or []),
            run_context=run_context or {},
            phase=phase,
        ),
    }
    try:
        raw_response = (transport or _openai_compatible_chat_completion)(request)
        answer = _answer_from_provider_response(raw_response)
    except Exception as exc:
        return _blocked_response(
            provider=provider,
            model=model,
            blocker="agent_response_provider_error",
            reasoning={**base_reasoning, "status": "error", "error_class": type(exc).__name__},
        )

    usage_record = _record_response_usage(raw_response, provider=provider, model=model)
    return AgentResponseSynthesis(
        answer=answer,
        ok=True,
        provider=provider,
        model=model,
        blockers=[],
        reasoning={
            **base_reasoning,
            "status": "ok",
                "usage": provider_usage(raw_response),
            "usage_recorded": bool(usage_record.get("recorded")),
            **({"usage_error_class": usage_record["error_class"]} if usage_record.get("error_class") else {}),
        },
    )


def _runtime_blocker(runtime: dict[str, Any], *, provider: str, context_pack: dict[str, Any]) -> str:
    if str(context_pack.get("status") or "") == "blocked":
        return "agent_response_context_blocked"
    block_reason = str(runtime.get("block_reason") or "")
    if block_reason == "provider_not_configured":
        return "agent_response_provider_not_configured"
    if block_reason == "provider_disabled" or not runtime.get("enabled", True):
        return "agent_response_provider_disabled"
    if block_reason == "unsupported_protocol":
        return "agent_response_provider_unsupported_protocol"
    if block_reason == "base_url_missing" or not str(runtime.get("base_url") or "").strip():
        return "agent_response_base_url_missing"
    if block_reason == "model_missing" or not str(runtime.get("model") or "").strip():
        return "agent_response_model_missing"
    if not provider:
        return "agent_response_provider_not_configured"
    return ""


def _blocked_response(*, provider: str, model: str, blocker: str, reasoning: dict[str, Any]) -> AgentResponseSynthesis:
    return AgentResponseSynthesis(
        answer=f"模型回复不可用：{blocker}。没有生成业务回答。",
        ok=False,
        provider=provider,
        model=model,
        blockers=[blocker],
        reasoning={**reasoning, "status": "blocked", "block_reason": blocker},
    )


def _response_messages(
    *,
    desk: str,
    ceo_message: str,
    plan_context: dict[str, Any],
    session_context: dict[str, Any],
    evidence_refs: list[str],
    action_refs: list[str],
    run_context: dict[str, Any],
    phase: str,
) -> list[dict[str, str]]:
    safe_context = {
        "phase": phase,
        "desk": desk,
        "ceo_message": ceo_message,
        "plan_context": _compact_provider_value(plan_context),
        "session_context": _compact_provider_value(session_context),
        "evidence_refs": evidence_refs,
        "action_refs": action_refs,
        "run_context": _compact_provider_value(run_context),
    }
    return [
        {
            "role": "system",
            "content": (
                "You are the desk response writer for Open Quant Company. "
                "Use only the supplied local facts, action results, blockers, and evidence references. "
                "Do not invent local system state, strategy metrics, data coverage, approvals, or tool results. "
                "If evidence is missing or a tool failed, say exactly what is missing and what command or artifact is needed. "
                "Write a direct, natural answer to the CEO in Chinese unless the CEO wrote in English. "
                "Return only a JSON object with an answer field and optional title/evidence_summary fields."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(safe_context, ensure_ascii=False, sort_keys=True),
        },
    ]


def _compact_provider_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        return "[truncated-depth]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_like_key(key_text):
                out[key_text] = "***REDACTED***"
            else:
                out[key_text] = _compact_provider_value(item, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [_compact_provider_value(item, depth=depth + 1) for item in value[:80]]
    if isinstance(value, tuple):
        return [_compact_provider_value(item, depth=depth + 1) for item in list(value)[:80]]
    if isinstance(value, str):
        return value if len(value) <= 6000 else value[:6000] + "\n...[truncated]"
    return value


def _is_secret_like_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(token in normalized for token in ("secret", "token", "password", "api_key", "apikey", "authorization", "credential"))


def _answer_from_provider_response(response: Any) -> str:
    if not isinstance(response, dict):
        raise ValueError("agent response provider response must be an object")
    content = provider_message_content(response)
    if isinstance(content, dict):
        answer = str(content.get("answer") or "").strip()
    else:
        text = str(content or "").strip()
        try:
            parsed = parse_json_object(text)
        except Exception:
            answer = text
        else:
            answer = str(parsed.get("answer") or text).strip()
    if not answer:
        raise ValueError("agent response provider returned empty answer")
    return answer


def _record_response_usage(response: Any, *, provider: str, model: str) -> dict[str, Any]:
    try:
        row = record_llm_response_usage(response, provider=provider, model=model, source=AGENT_RESPONSE_USE_CASE)
    except Exception as exc:
        return {"recorded": False, "error_class": type(exc).__name__}
    return {"recorded": bool(row), "error_class": ""}
