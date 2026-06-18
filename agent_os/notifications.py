from __future__ import annotations

from typing import Any, Callable

import requests

from core.env_secrets import read_env_secret


CHANNEL_SECRET_ENVS: dict[str, tuple[str, ...]] = {
    "telegram": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
    "wechat": ("WECHAT_WEBHOOK_URL",),
    "feishu": ("FEISHU_WEBHOOK_URL",),
}

NotificationSender = Callable[[str, dict[str, Any]], dict[str, Any]]


def supported_channels() -> list[str]:
    return list(CHANNEL_SECRET_ENVS)


def channel_secret_status(channel: str) -> dict[str, Any]:
    normalized = normalize_channel(channel)
    required = CHANNEL_SECRET_ENVS[normalized]
    missing = [name for name in required if not read_env_secret(name)]
    return {
        "channel": normalized,
        "required_env": list(required),
        "configured": not missing,
        "missing_env": missing,
    }


def normalize_channel(channel: str) -> str:
    normalized = str(channel or "").strip().lower()
    if normalized == "wecom":
        normalized = "wechat"
    if normalized not in CHANNEL_SECRET_ENVS:
        raise ValueError(f"Unsupported notification channel: {channel}")
    return normalized


def build_report_notification_message(report: dict[str, Any]) -> dict[str, Any]:
    sections = report.get("sections") or []
    open_work = next((section for section in sections if section.get("section_id") == "open_work"), {})
    return {
        "title": str(report.get("title") or "Open Quant Company Report"),
        "body": "\n".join(
            part
            for part in [
                str(report.get("summary") or "").strip(),
                str(open_work.get("body") or "").strip(),
                f"Report ID: {report.get('report_id')}",
                f"Evidence: {report.get('evidence_id') or 'none'}",
            ]
            if part
        ),
        "report_id": str(report.get("report_id") or ""),
        "report_kind": str(report.get("kind") or ""),
        "evidence_id": str(report.get("evidence_id") or ""),
        "path": str(report.get("path") or ""),
    }


def send_notification(channel: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_channel(channel)
    status = channel_secret_status(normalized)
    if not status["configured"]:
        return {
            "ok": False,
            "status": "missing_secret",
            "error": "missing notification environment variable",
            "missing_env": status["missing_env"],
        }

    message = _render_message(payload)
    try:
        if normalized == "telegram":
            response = requests.post(
                f"https://api.telegram.org/bot{read_env_secret('TELEGRAM_BOT_TOKEN')}/sendMessage",
                json={
                    "chat_id": read_env_secret("TELEGRAM_CHAT_ID"),
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
        elif normalized == "wechat":
            response = requests.post(
                read_env_secret("WECHAT_WEBHOOK_URL"),
                json={"msgtype": "markdown", "markdown": {"content": message}},
                timeout=10,
            )
        else:
            response = requests.post(
                read_env_secret("FEISHU_WEBHOOK_URL"),
                json={
                    "msg_type": "interactive",
                    "card": {
                        "header": {"title": {"content": str(payload.get("title") or "Open Quant Company Report"), "tag": "plain_text"}},
                        "elements": [{"tag": "markdown", "content": message}],
                    },
                },
                timeout=10,
            )
    except Exception as exc:
        return {"ok": False, "status": "failed", "error": str(exc), "status_code": None}

    ok = 200 <= int(response.status_code) < 300
    return {
        "ok": ok,
        "status": "sent" if ok else "failed",
        "status_code": int(response.status_code),
        "error": "" if ok else _safe_response_text(response.text),
    }


def _render_message(payload: dict[str, Any]) -> str:
    title = str(payload.get("title") or "Open Quant Company Report").strip()
    body = str(payload.get("body") or "").strip()
    report_id = str(payload.get("report_id") or "").strip()
    evidence_id = str(payload.get("evidence_id") or "").strip()
    lines = [f"*{title}*"]
    if body:
        lines.extend(["", body])
    if report_id:
        lines.extend(["", f"`{report_id}`"])
    if evidence_id:
        lines.append(f"Evidence: `{evidence_id}`")
    return "\n".join(lines)


def _safe_response_text(text: str) -> str:
    clean = str(text or "").strip()
    if len(clean) <= 240:
        return clean
    return clean[:240] + "...[truncated]"
