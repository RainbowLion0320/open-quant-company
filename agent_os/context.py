from __future__ import annotations

import hashlib
import json
import uuid
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.llm.usage import load_provider_api_key
from data.storage.datahub import get_datahub


DEFAULT_CONTEXT_WINDOW_TOKENS = 32768
WARN_THRESHOLD = 0.70
AUTO_COMPACT_THRESHOLD = 0.85
HARD_BLOCK_THRESHOLD = 0.95
TARGET_THRESHOLD = 0.60
RECENT_MESSAGE_COUNT = 12
SUMMARY_MESSAGE_LIMIT = 40
RECENT_CONTENT_LIMIT = 1200


def estimate_context_tokens(value: Any) -> int:
    """Cheap local token estimate used for prompt budgeting and UI telemetry."""
    if value is None:
        return 0
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return max(1, (len(text) + 3) // 4) if text else 0


def estimate_message_tokens(messages: list[dict[str, Any]]) -> int:
    payload = [
        {
            "role": str(message.get("role") or ""),
            "desk": str(message.get("desk") or ""),
            "content": str(message.get("content") or ""),
            "evidence_refs": list(message.get("evidence_refs") or []),
            "action_refs": list(message.get("action_refs") or []),
        }
        for message in messages
    ]
    return estimate_context_tokens(payload)


def context_window(runtime: dict[str, Any]) -> tuple[int, bool]:
    try:
        configured = int(runtime.get("context_window_tokens") or 0)
    except (TypeError, ValueError):
        configured = 0
    if configured > 0:
        return configured, False
    return DEFAULT_CONTEXT_WINDOW_TOKENS, True


def context_signature(messages: list[dict[str, Any]]) -> str:
    rows = []
    for message in messages:
        rows.append(
            {
                "message_id": str(message.get("message_id") or ""),
                "created_at": str(message.get("created_at") or ""),
                "role": str(message.get("role") or ""),
                "desk": str(message.get("desk") or ""),
                "content_sha256": hashlib.sha256(str(message.get("content") or "").encode("utf-8")).hexdigest(),
                "evidence_refs": list(message.get("evidence_refs") or []),
                "action_refs": list(message.get("action_refs") or []),
            }
        )
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def context_status(
    *,
    session_id: str,
    messages: list[dict[str, Any]],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    max_tokens, unknown_window = context_window(runtime)
    raw_tokens = estimate_message_tokens(messages)
    latest = latest_context_pack(session_id)
    latest_current = bool(latest and latest.get("input_signature") == context_signature(messages))
    status = _status_for_tokens(raw_tokens, max_tokens)
    effective_tokens = raw_tokens
    if latest_current:
        latest_status = str(latest.get("status") or "")
        if latest_status in {"compacted", "blocked", "ok", "warn"}:
            status = latest_status
        try:
            effective_tokens = int(latest.get("token_estimate", {}).get("effective_tokens") or raw_tokens)
        except (TypeError, ValueError, AttributeError):
            effective_tokens = raw_tokens
    return {
        "status": status,
        "session_id": session_id,
        "generated_at": _now(),
        "thresholds": _thresholds(max_tokens),
        "max_tokens": max_tokens,
        "unknown_window": unknown_window,
        "raw_tokens": raw_tokens,
        "effective_tokens": effective_tokens,
        "remaining_tokens": max(max_tokens - effective_tokens, 0),
        "usage_pct": round((effective_tokens / max_tokens) * 100, 2) if max_tokens else 0.0,
        "raw_usage_pct": round((raw_tokens / max_tokens) * 100, 2) if max_tokens else 0.0,
        "message_count": len(messages),
        "input_signature": context_signature(messages),
        "latest_pack": _latest_pack_summary(latest) if latest else None,
    }


def build_context_pack(
    *,
    session_id: str,
    messages: list[dict[str, Any]],
    runtime: dict[str, Any],
    force: bool = False,
    dry_run: bool = False,
    allow_provider_summary: bool = True,
    summary_transport: Any | None = None,
) -> dict[str, Any]:
    max_tokens, unknown_window = context_window(runtime)
    raw_tokens = estimate_message_tokens(messages)
    raw_status = _status_for_tokens(raw_tokens, max_tokens)
    must_compact = force or raw_tokens >= int(max_tokens * AUTO_COMPACT_THRESHOLD)
    signature = context_signature(messages)

    if not must_compact:
        return {
            "status": raw_status,
            "mode": "none",
            "session_id": session_id,
            "generated_at": _now(),
            "dry_run": dry_run,
            "input_signature": signature,
            "thresholds": _thresholds(max_tokens),
            "token_estimate": _token_estimate(
                raw_tokens=raw_tokens,
                effective_tokens=raw_tokens,
                max_tokens=max_tokens,
                unknown_window=unknown_window,
            ),
            "recent_messages": [_message_for_context(message) for message in messages[-RECENT_MESSAGE_COUNT:]],
            "summary": {},
            "artifact": None,
        }

    retained = messages[-RECENT_MESSAGE_COUNT:] if messages else []
    compressed = messages[: max(0, len(messages) - len(retained))]
    deterministic_summary = _deterministic_summary(compressed)
    provider_summary = _provider_summary(
        compressed,
        runtime=runtime,
        transport=summary_transport,
    ) if allow_provider_summary and compressed and not dry_run else {}
    pack_body = {
        "summary": {
            **deterministic_summary,
            **({"provider_summary": provider_summary} if provider_summary else {}),
        },
        "recent_messages": [_message_for_context(message) for message in retained],
        "refs": _refs_from_messages(messages),
    }
    effective_tokens = estimate_context_tokens(pack_body)
    trimmed_recent_count = len(retained)
    while effective_tokens > int(max_tokens * TARGET_THRESHOLD) and trimmed_recent_count > 6:
        trimmed_recent_count -= 1
        pack_body["recent_messages"] = [_message_for_context(message) for message in messages[-trimmed_recent_count:]]
        effective_tokens = estimate_context_tokens(pack_body)
    key_items = pack_body["summary"].get("key_items")
    while effective_tokens > int(max_tokens * TARGET_THRESHOLD) and isinstance(key_items, list) and len(key_items) > 4:
        del key_items[-1]
        effective_tokens = estimate_context_tokens(pack_body)
    timeline = pack_body["summary"].get("timeline")
    while effective_tokens > int(max_tokens * TARGET_THRESHOLD) and isinstance(timeline, list) and len(timeline) > 4:
        del timeline[0]
        effective_tokens = estimate_context_tokens(pack_body)
    if effective_tokens > int(max_tokens * TARGET_THRESHOLD) and trimmed_recent_count:
        pack_body["recent_messages"] = [
            _message_for_context(message, content_limit=360)
            for message in messages[-trimmed_recent_count:]
        ]
        effective_tokens = estimate_context_tokens(pack_body)
    if effective_tokens > int(max_tokens * TARGET_THRESHOLD) and trimmed_recent_count:
        pack_body["recent_messages"] = [
            _message_for_context(message, content_limit=180)
            for message in messages[-trimmed_recent_count:]
        ]
        effective_tokens = estimate_context_tokens(pack_body)

    status = "blocked" if effective_tokens >= int(max_tokens * HARD_BLOCK_THRESHOLD) else "compacted"
    block_reason = "context_pack_exceeds_hard_threshold" if status == "blocked" else ""
    payload = {
        "status": status,
        "mode": "hybrid" if provider_summary else "deterministic",
        "session_id": session_id,
        "generated_at": _now(),
        "dry_run": dry_run,
        "input_signature": signature,
        "provider": str(runtime.get("provider") or ""),
        "model": str(runtime.get("model") or ""),
        "thresholds": _thresholds(max_tokens),
        "token_estimate": _token_estimate(
            raw_tokens=raw_tokens,
            effective_tokens=effective_tokens,
            max_tokens=max_tokens,
            unknown_window=unknown_window,
        ),
        "message_count": len(messages),
        "compressed_message_count": len(compressed),
        "retained_message_count": len(pack_body["recent_messages"]),
        "compressed_message_ids": [str(message.get("message_id") or "") for message in compressed],
        "retained_message_ids": [str(message.get("message_id") or "") for message in retained[-trimmed_recent_count:]],
        "summary": pack_body["summary"],
        "recent_messages": pack_body["recent_messages"],
        "refs": pack_body["refs"],
        "block_reason": block_reason,
        "artifact": None,
    }
    if not dry_run:
        artifact_path = write_context_pack(payload)
        payload["artifact"] = {"path": str(artifact_path)}
    return payload


def write_context_pack(payload: dict[str, Any]) -> Path:
    root = _context_root() / _safe_session_id(str(payload.get("session_id") or "session"))
    root.mkdir(parents=True, exist_ok=True)
    filename_ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = root / f"context-pack-{filename_ts}-{uuid.uuid4().hex[:8]}.json"
    persisted = {**payload, "artifact": {"path": str(path)}}
    path.write_text(json.dumps(persisted, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    latest = root / "latest.json"
    latest.write_text(json.dumps(persisted, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def latest_context_pack(session_id: str) -> dict[str, Any] | None:
    path = _context_root() / _safe_session_id(session_id) / "latest.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _provider_summary(messages: list[dict[str, Any]], *, runtime: dict[str, Any], transport: Any | None = None) -> dict[str, Any]:
    if not _provider_available(runtime):
        return {}
    key = load_provider_api_key(str(runtime.get("provider") or ""))
    if not key:
        return {}
    request = {
        "provider": str(runtime.get("provider") or ""),
        "model": str(runtime.get("model") or ""),
        "base_url": str(runtime.get("base_url") or ""),
        "chat_path": str(runtime.get("chat_path") or "/chat/completions"),
        "api_key": key,
        "temperature": 0.0,
        "timeout_seconds": min(float(runtime.get("timeout_seconds", 20.0) or 20.0), 20.0),
        "response_format_json": bool(runtime.get("response_format_json", True)),
        "extra_body": runtime.get("extra_body") if isinstance(runtime.get("extra_body"), dict) else {},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Summarize Open Quant Company CEO Office conversation history for future planning. "
                    "Return JSON with summary, unresolved_items, decisions, and evidence_refs. "
                    "Do not invent facts; preserve ids and blockers."
                ),
            },
            {
                "role": "user",
                "content": json.dumps([_message_for_context(message, content_limit=900) for message in messages], ensure_ascii=False, sort_keys=True),
            },
        ],
    }
    try:
        response = (transport or _openai_compatible_chat_completion)(request)
    except Exception as exc:
        return {"status": "provider_summary_failed", "error_class": type(exc).__name__}
    content = _provider_response_content(response)
    parsed: Any
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {"summary": _clip(content, 2000)}
    if not isinstance(parsed, dict):
        parsed = {"summary": _clip(str(parsed), 2000)}
    return {
        "status": "ok",
        "provider": request["provider"],
        "model": request["model"],
        "summary": parsed,
    }


def _openai_compatible_chat_completion(request: dict[str, Any]) -> dict[str, Any]:
    base_url = str(request.get("base_url") or "").rstrip("/")
    chat_path = str(request.get("chat_path") or "/chat/completions")
    if not chat_path.startswith("/"):
        chat_path = f"/{chat_path}"
    payload = dict(request.get("extra_body") or {}) if isinstance(request.get("extra_body"), dict) else {}
    payload.update(
        {
            "model": str(request.get("model") or ""),
            "messages": request.get("messages") or [],
            "temperature": float(request.get("temperature", 0.0) or 0.0),
        }
    )
    if bool(request.get("response_format_json", True)):
        payload["response_format"] = {"type": "json_object"}
    http_request = urllib.request.Request(
        f"{base_url}{chat_path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {request.get('api_key')}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=float(request.get("timeout_seconds", 20.0) or 20.0)) as response:
        return json.loads(response.read().decode("utf-8"))


def _provider_available(runtime: dict[str, Any]) -> bool:
    return (
        bool(runtime.get("configured"))
        and bool(runtime.get("enabled", True))
        and str(runtime.get("protocol") or "") == "openai_compatible"
        and not str(runtime.get("block_reason") or "")
        and bool(str(runtime.get("base_url") or "").strip())
        and bool(str(runtime.get("model") or "").strip())
    )


def _provider_response_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            return str(message.get("content") or "")
        return str(choices[0].get("text") or "") if isinstance(choices[0], dict) else ""
    return ""


def _deterministic_summary(messages: list[dict[str, Any]]) -> dict[str, Any]:
    if not messages:
        return {
            "strategy": "deterministic_extract",
            "message_count": 0,
            "roles": {},
            "desks": {},
            "timeline": [],
            "key_items": [],
        }
    roles: dict[str, int] = {}
    desks: dict[str, int] = {}
    key_items: list[dict[str, Any]] = []
    timeline_source = [*messages[:3], *messages[-5:]]
    for message in messages:
        role = str(message.get("role") or "unknown")
        desk = str(message.get("desk") or "unknown")
        roles[role] = roles.get(role, 0) + 1
        desks[desk] = desks.get(desk, 0) + 1
        content = str(message.get("content") or "")
        if _is_key_content(content) or message.get("evidence_refs") or message.get("action_refs"):
            key_items.append(_message_for_context(message, content_limit=260))
    return {
        "strategy": "deterministic_extract",
        "message_count": len(messages),
        "roles": roles,
        "desks": desks,
        "timeline": [_message_for_context(message, content_limit=180) for message in timeline_source],
        "key_items": key_items[:SUMMARY_MESSAGE_LIMIT],
    }


def _message_for_context(message: dict[str, Any], *, content_limit: int = RECENT_CONTENT_LIMIT) -> dict[str, Any]:
    return {
        "message_id": str(message.get("message_id") or ""),
        "role": str(message.get("role") or ""),
        "desk": str(message.get("desk") or ""),
        "created_at": str(message.get("created_at") or ""),
        "content": _clip(str(message.get("content") or ""), content_limit),
        "evidence_refs": list(message.get("evidence_refs") or []),
        "action_refs": list(message.get("action_refs") or []),
    }


def _refs_from_messages(messages: list[dict[str, Any]]) -> dict[str, list[str]]:
    evidence: list[str] = []
    actions: list[str] = []
    for message in messages:
        evidence.extend(str(ref) for ref in (message.get("evidence_refs") or []) if str(ref).strip())
        actions.extend(str(ref) for ref in (message.get("action_refs") or []) if str(ref).strip())
    return {
        "evidence_refs": _ordered_unique(evidence),
        "action_refs": _ordered_unique(actions),
    }


def _ordered_unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _is_key_content(content: str) -> bool:
    normalized = content.lower()
    markers = (
        "blocked",
        "blocker",
        "failed",
        "approval",
        "approved",
        "rejected",
        "risk",
        "evidence",
        "decision",
        "缺",
        "阻断",
        "审批",
        "风险",
        "证据",
        "决定",
    )
    return any(marker in normalized for marker in markers)


def _status_for_tokens(tokens: int, max_tokens: int) -> str:
    if max_tokens <= 0:
        return "ok"
    if tokens >= int(max_tokens * HARD_BLOCK_THRESHOLD):
        return "warn"
    if tokens >= int(max_tokens * WARN_THRESHOLD):
        return "warn"
    return "ok"


def _thresholds(max_tokens: int) -> dict[str, Any]:
    return {
        "warn_pct": WARN_THRESHOLD,
        "auto_compact_pct": AUTO_COMPACT_THRESHOLD,
        "hard_block_pct": HARD_BLOCK_THRESHOLD,
        "target_pct": TARGET_THRESHOLD,
        "warn_tokens": int(max_tokens * WARN_THRESHOLD),
        "auto_compact_tokens": int(max_tokens * AUTO_COMPACT_THRESHOLD),
        "hard_block_tokens": int(max_tokens * HARD_BLOCK_THRESHOLD),
        "target_tokens": int(max_tokens * TARGET_THRESHOLD),
    }


def _token_estimate(*, raw_tokens: int, effective_tokens: int, max_tokens: int, unknown_window: bool) -> dict[str, Any]:
    return {
        "estimator": "chars_div_4",
        "max_tokens": max_tokens,
        "unknown_window": unknown_window,
        "raw_tokens": raw_tokens,
        "effective_tokens": effective_tokens,
        "remaining_tokens": max(max_tokens - effective_tokens, 0),
        "usage_pct": round((effective_tokens / max_tokens) * 100, 2) if max_tokens else 0.0,
        "raw_usage_pct": round((raw_tokens / max_tokens) * 100, 2) if max_tokens else 0.0,
    }


def _latest_pack_summary(pack: dict[str, Any]) -> dict[str, Any]:
    artifact = pack.get("artifact") if isinstance(pack.get("artifact"), dict) else {}
    estimate = pack.get("token_estimate") if isinstance(pack.get("token_estimate"), dict) else {}
    return {
        "status": str(pack.get("status") or ""),
        "mode": str(pack.get("mode") or ""),
        "generated_at": str(pack.get("generated_at") or ""),
        "artifact_path": str(artifact.get("path") or ""),
        "input_signature": str(pack.get("input_signature") or ""),
        "effective_tokens": int(estimate.get("effective_tokens") or 0),
        "raw_tokens": int(estimate.get("raw_tokens") or 0),
    }


def _context_root() -> Path:
    return get_datahub().artifact_dir("agent") / "context"


def _safe_session_id(session_id: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in session_id)
    return cleaned or "session"


def _clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
