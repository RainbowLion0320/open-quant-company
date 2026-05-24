"""
消息推送模块 — 支持 Telegram / 企业微信 / 飞书
配置: 星盘 config/notify.yaml 或环境变量
"""
import os, json, yaml, requests
from typing import List, Optional
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "notify.yaml")

def _load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, _load_config().get(key, default))


def send_telegram(message: str, token: str = "", chat_id: str = "") -> bool:
    """发送 Telegram 消息"""
    token = token or _env("TELEGRAM_BOT_TOKEN")
    chat_id = chat_id or _env("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def send_wechat_work(message: str, webhook: str = "") -> bool:
    """发送企业微信机器人消息"""
    webhook = webhook or _env("WECHAT_WEBHOOK_URL")
    if not webhook:
        return False

    try:
        r = requests.post(webhook, json={
            "msgtype": "markdown",
            "markdown": {"content": message},
        }, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def send_feishu(message: str, webhook: str = "") -> bool:
    """发送飞书机器人消息"""
    webhook = webhook or _env("FEISHU_WEBHOOK_URL")
    if not webhook:
        return False

    try:
        r = requests.post(webhook, json={
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"content": "星盘日报", "tag": "plain_text"}},
                "elements": [{"tag": "markdown", "content": message}],
            },
        }, timeout=10)
        return r.status_code == 200
    except Exception:
        return False


def push_report(title: str, body: str, channels: List[str] = None) -> dict:
    """
    推送到所有已配置渠道
    channels: ["telegram", "wechat", "feishu"]，默认全部
    """
    results = {}
    channels = channels or ["telegram", "wechat", "feishu"]

    full_msg = f"*{title}*\n{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n{body}"

    for ch in channels:
        if ch == "telegram":
            results["telegram"] = send_telegram(full_msg)
        elif ch == "wechat":
            results["wechat"] = send_wechat_work(full_msg)
        elif ch == "feishu":
            results["feishu"] = send_feishu(body)

    return results


def format_scan_report(passed: list, total: int, failed_moat: int, failed_margin: int) -> str:
    """格式化巴菲特扫描结果"""
    lines = [
        f"📊 股票池: {total} 只",
        f"✅ 通过: {len(passed)} 只 ({len(passed)/total*100:.1f}%)",
        f"❌ 护城河不足: {failed_moat} 只 | 安全边际不足: {failed_margin} 只",
        "",
        "🏆 精选池:",
    ]
    for r in sorted(passed, key=lambda x: -x.score)[:10]:
        lines.append(
            f"  `{r.symbol}` {r.name} · {r.score}分 · "
            f"ROE {r.avg_roe_5y*100:.1f}% · 安全边际 {r.safety_margin_pct*100:.1f}%"
        )
    if len(passed) > 10:
        lines.append(f"  ... 还有 {len(passed)-10} 只")
    return "\n".join(lines)
