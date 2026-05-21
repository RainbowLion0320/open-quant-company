"""系统配置路由 — 读写 config/settings.yaml"""

import os
import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/settings", tags=["Settings"])


# ── 配置文件路径 ──────────────────────────────────────────

def _config_path() -> str:
    """获取 config/settings.yaml 的绝对路径"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "config", "settings.yaml",
    )


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


# ── GET ────────────────────────────────────────────────────

@router.get("")
async def get_settings():
    """读取完整系统配置"""
    config = _read_config()
    return {
        "config": config,
        "path": _config_path(),
    }


# ── PUT ────────────────────────────────────────────────────

@router.put("")
async def update_settings(config: dict):
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

    try:
        _write_config(config)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config: {e}")

    return {
        "status": "saved",
        "path": _config_path(),
        "top_level_keys": list(config.keys()),
    }


@router.patch("/section/{section}")
async def update_section(section: str, data: dict):
    """部分更新：只修改指定配置段，不影响其他段"""
    config = _read_config()
    config[section] = data
    try:
        _write_config(config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to write config: {e}")
    return {"status": "saved", "section": section}
