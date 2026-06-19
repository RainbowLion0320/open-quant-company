from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from agent_os.desks import list_desks
from agent_os.llm_transport import openai_compatible_chat_completion
from agent_os.llm_transport import parse_json_object
from agent_os.llm_transport import provider_message_content
from agent_os.workflows import DeskRoutingDecision
from data.llm.usage import load_provider_api_key
from data.llm.usage import record_llm_response_usage
from data.llm.usage import resolve_llm_use_case


ROUTER_USE_CASE = "agent_routing"
VALID_DESKS = {str(desk.get("desk_id") or "") for desk in list_desks()}
_openai_compatible_chat_completion = openai_compatible_chat_completion


@dataclass(frozen=True)
class RouterDecision:
    primary_desk: str
    confidence: float
    matched_terms: list[str]
    reason: str
    intent: str = "provider_route"
    supporting_desks: list[str] = field(default_factory=list)
    needs_tool: bool = False
    router_source: str = "provider"
    block_reason: str = ""
    provider: str = ""
    model: str = ""

    def to_routing_decision(self) -> DeskRoutingDecision:
        return DeskRoutingDecision(
            assigned_desk=self.primary_desk,
            confidence=self.confidence,
            matched_terms=list(self.matched_terms),
            reason=self.reason,
            explicit=False,
        )

    def to_reasoning(self) -> dict[str, Any]:
        return {
            "kind": "agent_router",
            "router_source": self.router_source,
            "primary_desk": self.primary_desk,
            "supporting_desks": list(self.supporting_desks),
            "intent": self.intent,
            "confidence": self.confidence,
            "matched_terms": list(self.matched_terms),
            "reason": self.reason,
            "needs_tool": self.needs_tool,
            "block_reason": self.block_reason,
            "provider": self.provider,
            "model": self.model,
        }


class RouterAgent:
    """Provider-only CEO message router.

    The router only classifies intent and desk ownership. It never executes
    tools and never produces domain facts.
    """

    def __init__(self, *, transport: Any | None = None):
        self._transport = transport or _openai_compatible_chat_completion

    def route(self, content: str) -> RouterDecision:
        return self._provider_route(content=content)

    def _provider_route(self, *, content: str) -> RouterDecision:
        runtime = resolve_llm_use_case(ROUTER_USE_CASE)
        provider = str(runtime.get("provider") or "")
        model = str(runtime.get("model") or "")

        block_reason = _runtime_block_reason(runtime)
        if block_reason:
            return _blocked_decision(block_reason=block_reason, provider=provider, model=model)

        api_key = load_provider_api_key(provider)
        if not api_key:
            return _blocked_decision(block_reason="missing_secret", provider=provider, model=model)

        request = {
            "use_case": ROUTER_USE_CASE,
            "provider": provider,
            "model": model,
            "base_url": runtime["base_url"],
            "chat_path": runtime.get("chat_path", "/chat/completions"),
            "response_format_json": bool(runtime.get("response_format_json", True)),
            "temperature": float(runtime.get("temperature", 0.0) or 0.0),
            "extra_body": runtime.get("extra_body") if isinstance(runtime.get("extra_body"), dict) else {},
            "api_key": api_key,
            "timeout_seconds": float(runtime.get("timeout_seconds", 6.0) or 6.0),
            "messages": _router_messages(content=content),
        }
        try:
            response = self._transport(request)
            row = _provider_route_payload(response)
            decision = _validated_provider_decision(
                row,
                provider=provider,
                model=model,
            )
        except _RouterValidationError as exc:
            return _blocked_decision(block_reason=str(exc), provider=provider, model=model)
        except Exception as exc:
            return _blocked_decision(block_reason=f"provider_error:{type(exc).__name__}", provider=provider, model=model)

        try:
            record_llm_response_usage(response, provider=provider, model=model, source=ROUTER_USE_CASE)
        except Exception:
            pass
        return decision


class _RouterValidationError(ValueError):
    pass


def _blocked_decision(*, block_reason: str, provider: str = "", model: str = "") -> RouterDecision:
    return RouterDecision(
        primary_desk="",
        confidence=0.0,
        matched_terms=[],
        reason="agent routing provider did not return a valid route",
        intent="routing_blocked",
        supporting_desks=[],
        needs_tool=False,
        router_source="blocked",
        block_reason=block_reason,
        provider=provider,
        model=model,
    )


def _runtime_block_reason(runtime: dict[str, Any]) -> str:
    if runtime.get("block_reason") == "provider_not_configured":
        return "provider_not_configured"
    if runtime.get("block_reason") == "provider_disabled" or not runtime.get("enabled", True):
        return "provider_disabled"
    if runtime.get("block_reason") == "unsupported_protocol":
        return "unsupported_protocol"
    if runtime.get("block_reason") == "base_url_missing" or not runtime.get("base_url"):
        return "base_url_missing"
    if runtime.get("block_reason") == "model_missing" or not runtime.get("model"):
        return "model_missing"
    return ""


def _router_messages(*, content: str) -> list[dict[str, str]]:
    desks = [
        {
            "desk_id": str(desk.get("desk_id") or ""),
            "label": str(desk.get("display_name") or desk.get("desk_id") or ""),
            "mandate": str(desk.get("mandate") or ""),
        }
        for desk in list_desks()
    ]
    payload = {
        "message": content,
        "valid_desks": [desk["desk_id"] for desk in desks],
        "desks": desks,
        "required_schema": {
            "primary_desk": "one valid desk id",
            "supporting_desks": "array of valid desk ids",
            "intent": "short snake_case intent",
            "confidence": "0.0 to 0.95",
            "reason": "short factual routing reason",
            "needs_tool": "boolean",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You route CEO Office messages for Open Quant Company. "
                "Return only JSON. Do not answer the user's business question. "
                "Do not invent desks. Do not execute tools."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def _provider_route_payload(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise _RouterValidationError("provider_response_not_object")
    content = provider_message_content(response)
    if isinstance(content, dict):
        row = content
    else:
        row = parse_json_object(str(content or ""))
    if not isinstance(row, dict):
        raise _RouterValidationError("provider_payload_not_object")
    return row


def _validated_provider_decision(
    row: dict[str, Any],
    *,
    provider: str,
    model: str,
) -> RouterDecision:
    primary = str(row.get("primary_desk") or "").strip()
    if primary not in VALID_DESKS:
        raise _RouterValidationError("invalid_provider_primary_desk")
    supporting = _valid_supporting_desks(row.get("supporting_desks"), primary)
    confidence = _bounded_confidence(row.get("confidence"))
    intent = str(row.get("intent") or "provider_route").strip() or "provider_route"
    reason = str(row.get("reason") or "provider_structured_route").strip() or "provider_structured_route"
    return RouterDecision(
        primary_desk=primary,
        confidence=confidence,
        matched_terms=[],
        reason=reason,
        intent=intent,
        supporting_desks=supporting,
        needs_tool=bool(row.get("needs_tool")),
        router_source="provider",
        provider=provider,
        model=model,
    )


def _valid_supporting_desks(value: Any, primary: str) -> list[str]:
    rows = value if isinstance(value, list) else []
    out: list[str] = []
    for item in rows:
        desk = str(item).strip()
        if desk in VALID_DESKS and desk != primary and desk not in out:
            out.append(desk)
    return out[:4]


def _bounded_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.5
    return round(max(0.0, min(confidence, 0.95)), 2)
