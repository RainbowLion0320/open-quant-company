"""
策略注册表 — 唯一真理源

加载 config/settings.yaml → strategies 段, 提供统一查询接口。
所有硬编码策略名称的代码都应通过此模块获取策略列表。
"""
import yaml
import os
from typing import Dict, List, Optional

_REGISTRY: Optional[List[Dict]] = None


def _load_raw() -> dict:
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "config", "settings.yaml"
    )
    with open(config_path) as f:
        return yaml.safe_load(f)


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


if __name__ == "__main__":
    for s in load_registry():
        print(f"  {s['name']:>12} → {s['label']} ({s['color']}) [{s['config_key']}] {'✓' if s['enabled'] else '✗'}")
