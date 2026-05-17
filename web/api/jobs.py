"""异步任务队列 — 策略运行后台执行 + WebSocket 进度推送"""

import uuid
import threading
import logging
from typing import Dict, Optional, Callable
from datetime import datetime

logger = logging.getLogger("quant-agent.jobs")

# job_id -> JobInfo
_jobs: Dict[str, dict] = {}
_lock = threading.Lock()


def create_job(strategy: str, limit: int = 0, params: dict = None) -> str:
    job_id = str(uuid.uuid4())[:8]
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "strategy": strategy,
            "status": "pending",
            "progress": 0,
            "message": f"Queued: {strategy} (limit={limit})",
            "result": None,
            "params": params or {},
            "limit": limit,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
        }
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    return _jobs.get(job_id)


def update_job(job_id: str, **kwargs):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def run_job(job_id: str, target: Callable, *args, **kwargs):
    """在后台线程执行任务，通过回调更新进度"""
    update_job(job_id, status="running", started_at=datetime.now().isoformat())

    def _runner():
        try:
            result = target(*args, **kwargs)
            update_job(job_id, status="done", progress=100,
                       message="Completed", result=result,
                       completed_at=datetime.now().isoformat())
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            update_job(job_id, status="error", message=str(e),
                       completed_at=datetime.now().isoformat())

    t = threading.Thread(target=_runner, daemon=True, name=f"job-{job_id}")
    t.start()


async def run_strategy_async(strategy: str, limit: int = 0, params: dict = None) -> str:
    """异步启动策略运行，返回 job_id"""
    job_id = create_job(strategy, limit, params)

    def _run():
        from data.results_db import init
        from data.strategy_plugins import run_registered_strategies

        init()

        def progress_callback(current, total, message=""):
            pct = int(current / total * 100) if total > 0 else 0
            update_job(job_id, progress=pct, message=message or f"{current}/{total}")

        return {"strategies": run_registered_strategies(strategy, limit, progress_callback)}

    run_job(job_id, _run)
    return job_id
