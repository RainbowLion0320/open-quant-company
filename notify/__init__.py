from __future__ import annotations

from datetime import datetime
from typing import Any

from agent_os.notifications import build_report_notification_message, send_notification, supported_channels


def send_telegram(message: str) -> bool:
    return bool(send_notification("telegram", {"title": "Open Quant Company", "body": message}).get("ok"))


def send_wechat_work(message: str) -> bool:
    return bool(send_notification("wechat", {"title": "Open Quant Company", "body": message}).get("ok"))


def send_feishu(message: str) -> bool:
    return bool(send_notification("feishu", {"title": "Open Quant Company", "body": message}).get("ok"))


def push_report(title: str, body: str, channels: list[str] | None = None) -> dict[str, bool]:
    payload = {
        "title": title,
        "body": f"{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{body}",
        "report_id": "",
        "evidence_id": "",
    }
    results: dict[str, bool] = {}
    for channel in channels or supported_channels():
        result = send_notification(channel, payload)
        results[channel] = bool(result.get("ok"))
    return results


def format_scan_report(passed: list[Any], total: int, failed_moat: int, failed_margin: int) -> str:
    lines = [
        f"股票池: {total} 只",
        f"通过: {len(passed)} 只 ({len(passed) / total * 100:.1f}%)",
        f"护城河不足: {failed_moat} 只 | 安全边际不足: {failed_margin} 只",
        "",
        "精选池:",
    ]
    for row in sorted(passed, key=lambda item: -item.score)[:10]:
        lines.append(
            f"  `{row.symbol}` {row.name} · {row.score}分 · "
            f"ROE {row.avg_roe_5y * 100:.1f}% · 安全边际 {row.safety_margin_pct * 100:.1f}%"
        )
    if len(passed) > 10:
        lines.append(f"  ... 还有 {len(passed) - 10} 只")
    return "\n".join(lines)


def format_agent_report_notification(report: dict[str, Any]) -> dict[str, Any]:
    return build_report_notification_message(report)
