from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from agent_os.desks import get_desk
from agent_os.desks import list_desks
from agent_os.llm_transport import openai_compatible_chat_completion
from agent_os.llm_transport import parse_json_object
from agent_os.llm_transport import provider_message_content
from agent_os.tools import AgentToolRegistry
from data.llm.usage import load_provider_api_key
from data.llm.usage import record_llm_response_usage
from data.llm.usage import resolve_llm_use_case


TOOL_PLANNING_USE_CASE = "agent_tool_planning"
_openai_compatible_chat_completion = openai_compatible_chat_completion


@dataclass(frozen=True)
class AcceptedToolCall:
    desk: str
    tool_id: str
    action_type: str
    risk_level: str
    summary: str
    expected_effect: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolPlanningResult:
    desk: str
    intent: str
    confidence: float
    actions: list[AcceptedToolCall]
    blockers: list[str]
    reasoning: dict[str, Any]
    planning_mode: str


class ToolPlanningAgent:
    """Provider-only fixed-registry tool planner for CEO Office messages."""

    def __init__(self, *, transport: Any | None = None, registry: AgentToolRegistry | None = None):
        self._transport = transport or _openai_compatible_chat_completion
        self._registry = registry or AgentToolRegistry()

    def plan(
        self,
        *,
        desk: str,
        content: str,
        router_reasoning: dict[str, Any] | None = None,
        artifact_context: dict[str, Any] | None = None,
        session_context: dict[str, Any] | None = None,
    ) -> ToolPlanningResult:
        runtime = resolve_llm_use_case(TOOL_PLANNING_USE_CASE)
        provider = str(runtime.get("provider") or "")
        model = str(runtime.get("model") or "")
        base_reasoning = {
            "kind": "agent_tool_planner",
            "use_case": TOOL_PLANNING_USE_CASE,
            "provider": provider,
            "model": model,
            "accepted_tool_count": 0,
            "rejected_tool_count": 0,
        }
        block_reason = _runtime_block_reason(runtime)
        if block_reason:
            return _blocked_result(desk=desk, blocker=f"agent_tool_planning_{block_reason}", reasoning=base_reasoning)

        api_key = load_provider_api_key(provider)
        if not api_key:
            return _blocked_result(desk=desk, blocker="agent_tool_planning_missing_secret", reasoning=base_reasoning)

        request = {
            "use_case": TOOL_PLANNING_USE_CASE,
            "provider": provider,
            "model": model,
            "base_url": str(runtime.get("base_url") or ""),
            "chat_path": str(runtime.get("chat_path") or "/chat/completions"),
            "response_format_json": bool(runtime.get("response_format_json", True)),
            "temperature": float(runtime.get("temperature", 0.0) or 0.0),
            "extra_body": runtime.get("extra_body") if isinstance(runtime.get("extra_body"), dict) else {},
            "api_key": api_key,
            "timeout_seconds": float(runtime.get("timeout_seconds", 10.0) or 10.0),
            "messages": _tool_planning_messages(
                desk=desk,
                content=content,
                tools=self._registry.list(),
                router_reasoning=router_reasoning or {},
                artifact_context=artifact_context or {},
                session_context=session_context or {},
            ),
        }
        try:
            response = self._transport(request)
            payload = _provider_plan_payload(response)
        except _ToolPlanningValidationError as exc:
            return _blocked_result(
                desk=desk,
                blocker=f"agent_tool_planning_{exc}",
                reasoning={**base_reasoning, "status": "blocked", "block_reason": str(exc)},
            )
        except Exception as exc:
            return _blocked_result(
                desk=desk,
                blocker=f"agent_tool_planning_provider_error:{type(exc).__name__}",
                reasoning={**base_reasoning, "status": "blocked", "block_reason": f"provider_error:{type(exc).__name__}"},
            )

        result = self._validate_payload(payload, desk=desk)
        try:
            record_llm_response_usage(response, provider=provider, model=model, source=TOOL_PLANNING_USE_CASE)
        except Exception:
            pass
        planning_mode = "llm_tool_planning" if result["actions"] else "llm_no_tool_required"
        return ToolPlanningResult(
            desk=desk,
            intent=result["intent"],
            confidence=result["confidence"],
            actions=result["actions"],
            blockers=result["blockers"],
            reasoning={
                **base_reasoning,
                "status": "ok" if not result["blockers"] else "blocked",
                "intent": result["intent"],
                "reason": result["reason"],
                "accepted_tool_ids": [action.tool_id for action in result["actions"]],
                "accepted_tool_count": len(result["actions"]),
                "rejected_tool_count": len(result["rejected"]),
                "rejected": result["rejected"],
            },
            planning_mode=planning_mode if not result["blockers"] else "tool_planning_blocked",
        )

    def _validate_payload(self, payload: dict[str, Any], *, desk: str) -> dict[str, Any]:
        primary = str(payload.get("primary_desk") or desk).strip()
        if primary and primary != desk:
            blocker = f"agent_tool_planning_primary_desk_mismatch:{primary}"
            return {
                "intent": str(payload.get("intent") or "tool_plan"),
                "confidence": 0.0,
                "reason": str(payload.get("reason") or ""),
                "actions": [],
                "rejected": [{"tool_id": "", "reason": blocker}],
                "blockers": [blocker],
            }

        intent = str(payload.get("intent") or "tool_plan").strip() or "tool_plan"
        reason = str(payload.get("reason") or "").strip()
        actions: list[AcceptedToolCall] = []
        rejected: list[dict[str, str]] = []
        blockers: list[str] = []
        for raw_call in payload.get("tool_calls") if isinstance(payload.get("tool_calls"), list) else []:
            call = raw_call if isinstance(raw_call, dict) else {}
            tool_id = str(call.get("tool_id") or "").strip()
            descriptor = self._registry.get(tool_id)
            if descriptor is None:
                blocker = f"agent_tool_planning_unknown_tool:{tool_id}"
                rejected.append({"tool_id": tool_id, "reason": blocker})
                blockers.append(blocker)
                continue
            if desk not in set(descriptor.desk_scopes):
                blocker = f"agent_tool_planning_invalid_tool_scope:{tool_id}"
                rejected.append({"tool_id": tool_id, "reason": blocker})
                blockers.append(blocker)
                continue
            desk_record = get_desk(desk) or {}
            if tool_id not in set(desk_record.get("allowed_tools", [])):
                blocker = f"agent_tool_planning_invalid_tool_scope:{tool_id}"
                rejected.append({"tool_id": tool_id, "reason": blocker})
                blockers.append(blocker)
                continue
            parameters, parameter_error = _validated_parameters(call.get("parameters"), descriptor.parameter_patterns)
            if parameter_error:
                blocker = f"agent_tool_planning_{parameter_error}:{tool_id}"
                rejected.append({"tool_id": tool_id, "reason": blocker})
                blockers.append(blocker)
                continue
            actions.append(
                AcceptedToolCall(
                    desk=desk,
                    tool_id=tool_id,
                    action_type=_action_type_for_tool(tool_id),
                    risk_level=descriptor.risk_level,
                    summary=str(call.get("summary") or descriptor.label).strip() or descriptor.label,
                    expected_effect=str(call.get("expected_effect") or f"Run fixed registry tool {tool_id}.").strip(),
                    parameters=parameters,
                )
            )
        return {
            "intent": intent,
            "confidence": _bounded_confidence(payload.get("confidence")),
            "reason": reason,
            "actions": actions,
            "rejected": rejected,
            "blockers": blockers,
        }


class _ToolPlanningValidationError(ValueError):
    pass


def _blocked_result(*, desk: str, blocker: str, reasoning: dict[str, Any]) -> ToolPlanningResult:
    return ToolPlanningResult(
        desk=desk,
        intent="tool_planning_blocked",
        confidence=0.0,
        actions=[],
        blockers=[blocker],
        reasoning={**reasoning, "status": "blocked", "block_reason": blocker},
        planning_mode="tool_planning_blocked",
    )


def _runtime_block_reason(runtime: dict[str, Any]) -> str:
    if runtime.get("block_reason") == "provider_not_configured":
        return "provider_not_configured"
    if runtime.get("block_reason") == "provider_disabled" or not runtime.get("enabled", True):
        return "provider_disabled"
    if runtime.get("block_reason") == "unsupported_protocol":
        return "provider_unsupported_protocol"
    if runtime.get("block_reason") == "base_url_missing" or not str(runtime.get("base_url") or "").strip():
        return "base_url_missing"
    if runtime.get("block_reason") == "model_missing" or not str(runtime.get("model") or "").strip():
        return "model_missing"
    return ""


def _tool_planning_messages(
    *,
    desk: str,
    content: str,
    tools: list[dict[str, Any]],
    router_reasoning: dict[str, Any],
    artifact_context: dict[str, Any],
    session_context: dict[str, Any],
) -> list[dict[str, str]]:
    payload = {
        "ceo_message": content,
        "desk": desk,
        "valid_desks": [str(row.get("desk_id") or "") for row in list_desks()],
        "fixed_tools": tools,
        "router_reasoning": router_reasoning,
        "artifact_context": _compact_context(artifact_context),
        "session_context": _compact_context(session_context),
        "required_schema": {
            "primary_desk": desk,
            "intent": "short snake_case intent",
            "tool_calls": [{"tool_id": "one fixed tool_id", "summary": "short", "expected_effect": "short", "parameters": {}}],
            "requires_approval": "boolean",
            "clarifying_question": "string, empty when not needed",
            "reason": "short factual reason",
        },
    }
    return [
        {
            "role": "system",
            "content": (
                "You choose fixed registry tools for Open Quant Company. "
                "Return only JSON. Do not answer the CEO. Do not invent tool ids. "
                "Use only tool ids from fixed_tools and only when they fit the user's request."
            ),
        },
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)},
    ]


def _provider_plan_payload(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise _ToolPlanningValidationError("provider_response_not_object")
    content = provider_message_content(response)
    if isinstance(content, dict):
        row = content
    else:
        row = parse_json_object(str(content or ""))
    if not isinstance(row, dict):
        raise _ToolPlanningValidationError("provider_payload_not_object")
    return row


def _validated_parameters(value: Any, patterns: dict[str, str]) -> tuple[dict[str, Any], str]:
    raw = value if isinstance(value, dict) else {}
    if not patterns:
        return {}, ""
    out: dict[str, Any] = {}
    for name, pattern in patterns.items():
        text = str(raw.get(name) or "").strip()
        if not text:
            return {}, f"missing_tool_parameter:{name}"
        if not re.fullmatch(pattern, text):
            return {}, f"invalid_tool_parameter:{name}"
        out[name] = text
    return out, ""


def _action_type_for_tool(tool_id: str) -> str:
    return tool_id.removeprefix("astroq.").replace(".", "_").replace("-", "_")


def _bounded_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.5
    return round(max(0.0, min(confidence, 0.95)), 2)


def _compact_context(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        return "[truncated-depth]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:40]:
            out[str(key)] = _compact_context(item, depth=depth + 1)
        return out
    if isinstance(value, list):
        return [_compact_context(item, depth=depth + 1) for item in value[:30]]
    if isinstance(value, str):
        return value[:2000] + ("...[truncated]" if len(value) > 2000 else "")
    return value
