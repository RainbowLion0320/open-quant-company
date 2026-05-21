"""
Cron 作业错误可观测性 — 统一记录 cron 脚本的运行状态和错误

用法:
    from data.cron_logger import cron_run

    with cron_run("cron_fetch_daily"):
        # ... your cron logic ...
        pass

    # 或手动记录:
    from data.cron_logger import log_cron_error, log_cron_success
    log_cron_success("compute_signals", stocks_scanned=200)
    log_cron_error("cron_fetch_daily", error="Tushare rate limited")
"""
import json
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from data.datahub import get_datahub

_HUB = get_datahub()
_LOG_DIR = _HUB.store_root / "_cron_log"


def _ensure_dir():
    _LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_cron_success(script: str, **extra):
    _ensure_dir()
    entry = {
        "script": script,
        "status": "ok",
        "ts": datetime.now().isoformat(),
        **extra,
    }
    _append_log(script, entry)


def log_cron_error(script: str, error: str, tb: str = "", **extra):
    _ensure_dir()
    entry = {
        "script": script,
        "status": "error",
        "error": error[:500],
        "traceback": tb[:2000],
        "ts": datetime.now().isoformat(),
        **extra,
    }
    _append_log(script, entry)


def _append_log(script: str, entry: dict):
    log_file = _LOG_DIR / f"{script}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _rotate_if_needed(log_file)


def _rotate_if_needed(path: Path, max_lines: int = 500):
    try:
        lines = path.read_text().splitlines()
        if len(lines) > max_lines:
            path.write_text("\n".join(lines[-max_lines:]) + "\n")
    except Exception:
        pass


@contextmanager
def cron_run(script: str):
    """Context manager that logs success/failure of a cron job."""
    t0 = time.monotonic()
    try:
        yield
        elapsed = time.monotonic() - t0
        log_cron_success(script, elapsed_s=round(elapsed, 1))
    except Exception as e:
        elapsed = time.monotonic() - t0
        log_cron_error(
            script,
            error=str(e),
            tb=traceback.format_exc(),
            elapsed_s=round(elapsed, 1),
        )
        raise


def get_recent_errors(limit: int = 20) -> list[dict]:
    """读取最近的 cron 错误（供 Web API 展示）"""
    _ensure_dir()
    errors = []
    for log_file in _LOG_DIR.glob("*.jsonl"):
        try:
            for line in log_file.read_text().splitlines()[-50:]:
                entry = json.loads(line)
                if entry.get("status") == "error":
                    errors.append(entry)
        except Exception:
            continue
    errors.sort(key=lambda x: x.get("ts", ""), reverse=True)
    return errors[:limit]
