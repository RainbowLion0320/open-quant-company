"""
策略注册表 — 唯一真理源

加载 config/settings.yaml → strategies 段, 提供统一查询接口。
所有硬编码策略名称的代码都应通过此模块获取策略列表。

P2-12: 策略晋级制度 — 5 状态生命周期 (candidate→validated→paper→production→retired)
"""

from typing import Dict, List, Optional

from core.settings import get_settings

_REGISTRY: Optional[List[Dict]] = None

# Status lifecycle ordering (ordered by maturity)
ALLOWED_STATUSES = ("candidate", "validated", "paper", "production", "retired")
_STATUS_RANK = {s: i for i, s in enumerate(ALLOWED_STATUSES)}

# Valid promotion transitions
VALID_PROMOTIONS = {
    "candidate": {"validated"},
    "validated": {"paper"},
    "paper": {"production", "retired"},
    "production": {"retired"},
    "retired": set(),
}

# What each status allows
STATUS_CAPABILITIES = {
    "candidate":  {"backtest", "scan"},
    "validated":  {"backtest", "scan", "tournament"},
    "paper":      {"backtest", "scan", "tournament", "paper_trading"},
    "production": {"backtest", "scan", "tournament", "paper_trading", "production"},
    "retired":    set(),
}


def _load_raw() -> dict:
    return get_settings()


def load_registry(force_reload: bool = False) -> List[Dict]:
    """返回所有注册策略的元数据列表"""
    global _REGISTRY
    if _REGISTRY is not None and not force_reload:
        return _REGISTRY

    cfg = _load_raw()
    raw = cfg.get("strategies", {})
    _REGISTRY = [
        {
            "name": name,
            "label": v.get("label", name),
            "color": v.get("color", "#7170ff"),
            "config_key": v.get("config_key", name),
            "runner": v.get("runner", ""),
            "signal_name": v.get("signal_name", name),
            "enabled": v.get("enabled", True),
            "status": v.get("status", "candidate"),
        }
        for name, v in raw.items()
    ]
    return _REGISTRY


def get_enabled_strategies() -> List[Dict]:
    """只返回 enabled=true 的策略"""
    return [s for s in load_registry() if s.get("enabled", True)]


def get_strategy(name: str) -> Optional[Dict]:
    """按名查找策略"""
    for s in load_registry():
        if s["name"] == name:
            return s
    return None


def get_strategy_label(name: str) -> str:
    """策略名 → 中文标签"""
    s = get_strategy(name)
    return s["label"] if s else name


def get_strategy_color(name: str) -> str:
    """策略名 → 显示颜色"""
    s = get_strategy(name)
    return s.get("color", "#7170ff") if s else "#7170ff"


def get_strategy_config(cfg: dict, name: str) -> dict:
    """从完整 config 中提取某策略的配置段"""
    s = get_strategy(name)
    if not s:
        return {}
    key = s["config_key"]
    # 支持嵌套路径, 如 "signals.multifactor"
    keys = key.split(".")
    val = cfg
    for k in keys:
        val = val.get(k, {})
    return val if isinstance(val, dict) else {}


def list_strategy_names(include_disabled: bool = False) -> List[str]:
    """返回所有策略名"""
    src = load_registry() if include_disabled else get_enabled_strategies()
    return [s["name"] for s in src]


# ── P2-12: Status-aware queries ──

def get_by_status(status: str) -> List[Dict]:
    """返回指定 status 的所有 enabled 策略."""
    if status not in ALLOWED_STATUSES:
        return []
    return [s for s in get_enabled_strategies() if s.get("status") == status]


def get_status(name: str) -> str:
    """返回策略的当前 status, 默认 candidate."""
    s = get_strategy(name)
    return s.get("status", "candidate") if s else "candidate"


def status_rank(name: str) -> int:
    """返回策略 status 的排序权重 (越高越成熟)."""
    return _STATUS_RANK.get(get_status(name), 0)


def can_run_paper(name: str) -> bool:
    """策略是否可以参与 paper trading (status >= paper)."""
    return status_rank(name) >= _STATUS_RANK["paper"]


def can_run_production(name: str) -> bool:
    """策略是否可以用于生产信号 (status == production)."""
    return get_status(name) == "production"


def can_run_tournament(name: str) -> bool:
    """策略是否可以参加锦标赛 (status >= validated)."""
    s = get_strategy(name)
    if not s or not s.get("enabled", True):
        return False
    return status_rank(name) >= _STATUS_RANK["validated"]


def validate_promotion(name: str, new_status: str) -> tuple[bool, str]:
    """校验策略晋级是否合法。返回 (valid, reason)."""
    current = get_status(name)
    if current not in VALID_PROMOTIONS:
        return False, f"Unknown current status: {current}"
    if new_status not in ALLOWED_STATUSES:
        return False, f"Unknown target status: {new_status}"
    if new_status not in VALID_PROMOTIONS.get(current, set()):
        return False, f"Invalid promotion: {current} → {new_status}. Allowed: {VALID_PROMOTIONS.get(current, set())}"
    return True, "ok"


def status_label(status: str) -> str:
    """中文标签映射."""
    return {
        "candidate": "候选",
        "validated": "已验证",
        "paper": "模拟盘",
        "production": "生产",
        "retired": "已退役",
    }.get(status, status)


if __name__ == "__main__":
    for s in load_registry():
        st = s.get("status", "candidate")
        print(f"  {s['name']:>12} → {s['label']} [{st}] ({s['color']}) {'✓' if s['enabled'] else '✗'}")
