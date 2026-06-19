from __future__ import annotations

import json
import re
import urllib.request
from typing import Any


def openai_compatible_chat_completion(request: dict[str, Any]) -> dict[str, Any]:
    base_url = str(request.get("base_url") or "").rstrip("/")
    chat_path = str(request.get("chat_path") or "/chat/completions")
    if not chat_path.startswith("/"):
        chat_path = f"/{chat_path}"
    url = f"{base_url}{chat_path}"
    extra_body = request.get("extra_body")
    payload = dict(extra_body) if isinstance(extra_body, dict) else {}
    payload.update(
        {
            "model": str(request.get("model") or ""),
            "messages": request.get("messages") or [],
            "temperature": float(request.get("temperature", 0.1) or 0.1),
        }
    )
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


def provider_message_content(response: dict[str, Any]) -> Any:
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


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def provider_usage(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return {}
    return {str(key): value for key, value in usage.items() if isinstance(value, int | float | str)}
