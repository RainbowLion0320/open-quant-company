"""系统配置路由 — 读写 config/settings.yaml (auth + audit)"""

import os
import yaml
from fastapi import APIRouter, HTTPException, Request

from core.settings import clear_settings_cache, resolve_settings_path

router = APIRouter(prefix="/api/settings", tags=["Settings"])


# ── 配置文件路径 ──────────────────────────────────────────

def _config_path() -> str:
    """获取 config/settings.yaml 的绝对路径"""
    return str(resolve_settings_path())


def _read_config() -> dict:
    """读取配置, 不存在则返回空"""
    path = _config_path()
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _write_config(data: dict):
    """写回配置, 保留格式 (PyYAML Dumper)"""
    path = _config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # 备份原文件
    bak = path + ".bak"
    if os.path.exists(path):
        with open(path, "r") as src:
            with open(bak, "w") as dst:
                dst.write(src.read())

    try:
        with open(path, "w") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        clear_settings_cache()
    except Exception:
        # 写入失败时恢复备份
        if os.path.exists(bak):
            with open(bak, "r") as src:
                with open(path, "w") as dst:
                    dst.write(src.read())
        raise

    # 写入成功后删除备份
    if os.path.exists(bak):
        os.remove(bak)


# ── Run mode check ──

RUN_MODE_READONLY_SECTIONS = frozenset({
    "risk_control", "strategies", "data_registry", "backtest",
    "buffett", "cybernetics", "signals", "signal_selection",
    "ml", "assets", "asset_allocation", "trading", "data_cleaning",
})


def _check_writable(section: str) -> None:
    """Raise 403 if current run mode disallows writing to this section."""
    from web.api.auth import get_run_mode

    mode = get_run_mode()
    if mode == "live":
        raise HTTPException(
            status_code=403,
            detail="Settings are read-only in live mode. "
                   "Switch to research or paper mode in config file."
        )
    if mode == "paper" and section != "paper_trading":
        raise HTTPException(
            status_code=403,
            detail=f"Only 'paper_trading' section is writable in paper mode. "
                   f"Section '{section}' requires research mode."
        )


def _audit_change(request: Request, section: str, method: str, old_data: dict, new_data: dict):
    """Record config change to audit ledger."""
    try:
        from data.audit import ConfigAuditLedger
        from web.api.auth import get_run_mode

        ledger = ConfigAuditLedger()
        ledger.record(
            section=section,
            method=method,
            old_data=old_data,
            new_data=new_data,
            source_ip=request.client.host if request.client else "",
            user_agent=request.headers.get("user-agent", ""),
            run_mode=get_run_mode(),
        )
    except Exception:
        pass  # audit failure must not block config writes


# ── GET ────────────────────────────────────────────────────

@router.get("")
async def get_settings():
    """读取完整系统配置"""
    config = _read_config()
    return {
        "config": config,
        "path": _config_path(),
    }


@router.get("/schema")
async def get_settings_schema():
    """返回配置中心 schema — 每个可编辑 section 的参数元数据"""
    from web.api.settings_schema import get_settings_schema
    return get_settings_schema()


# ── PUT ────────────────────────────────────────────────────

@router.put("")
async def update_settings(config: dict, request: Request):
    """完全替换系统配置（谨慎操作）

    请求体应为完整的 YAML 配置字典。
    写入前会自动备份原文件到 config/settings.yaml.bak。
    必须包含核心配置段，防止误删关键配置。
    """
    if not config:
        raise HTTPException(status_code=400, detail="Empty config body")

    REQUIRED_SECTIONS = {"strategies", "risk_control"}
    missing = REQUIRED_SECTIONS - set(config.keys())
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required config sections: {missing}. "
                   f"Use PATCH /api/settings/section for partial updates.",
        )

    # Check run mode
    _check_writable("*")

    old_config = _read_config()

    try:
        _write_config(config)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config: {e}")

    _audit_change(request, "*", "PUT", old_config, config)

    return {
        "status": "saved",
        "path": _config_path(),
        "top_level_keys": list(config.keys()),
    }


@router.patch("/section/{section}")
async def update_section(section: str, data: dict, request: Request):
    """部分更新：只修改指定配置段，不影响其他段"""
    _check_writable(section)

    # Validate against schema if available
    errors = _validate_section(section, data)
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    config = _read_config()
    old_section = config.get(section, {})

    config[section] = data
    try:
        _write_config(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config: {e}")

    _audit_change(request, section, "PATCH", old_section, data)

    return {"status": "saved", "section": section}


def _validate_section(section: str, data: dict) -> list[str]:
    """Validate section data against schema. Returns list of error messages."""
    from web.api.settings_schema import SETTINGS_SECTIONS

    errors = []
    schema = next((s for s in SETTINGS_SECTIONS if s["key"] == section), None)
    if not schema:
        return []  # No schema = no validation

    for field in schema["fields"]:
        key = field["key"]
        # Support dotted keys (e.g., "max_single_position.max_pct")
        parts = key.split(".")
        val = data
        for p in parts:
            if isinstance(val, dict):
                val = val.get(p)
            else:
                val = None
                break

        if val is None:
            continue  # Missing = use default, not an error

        ftype = field.get("type", "float")
        fmin = field.get("min")
        fmax = field.get("max")

        # Type check
        if ftype == "int" and not isinstance(val, int):
            try:
                val = int(val)
            except (ValueError, TypeError):
                errors.append(f"{key}: expected int, got {type(val).__name__}")
                continue
        elif ftype == "float" and not isinstance(val, (int, float)):
            try:
                val = float(val)
            except (ValueError, TypeError):
                errors.append(f"{key}: expected float, got {type(val).__name__}")
                continue

        # Range check
        if fmin is not None and val < fmin:
            errors.append(f"{key}: {val} < min ({fmin})")
        if fmax is not None and val > fmax:
            errors.append(f"{key}: {val} > max ({fmax})")

    return errors
