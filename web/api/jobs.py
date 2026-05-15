"""异步任务队列 — 策略运行后台执行 + WebSocket 进度推送"""

import asyncio
import uuid
import threading
import time
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
        import sys, os
        sys.path.insert(0, os.path.expanduser("~/quant-agent"))

        from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR, SYMBOL_NAME
        from data.financials import get_buffett_inputs
        from data.results_db import save_buffett_results, save_strategy_signals, init
        from data.registry import get_enabled_strategies

        init()

        def progress_callback(current, total, message=""):
            pct = int(current / total * 100) if total > 0 else 0
            update_job(job_id, progress=pct, message=message or f"{current}/{total}")

        # ── 策略→运行函数映射 ──
        _run_map = {
            "buffett": _run_buffett,
            "multifactor": _run_multifactor,
            "cybernetic": _run_cybernetic,
            "ml_lgbm": _run_ml_lgbm,
        }

        for s in get_enabled_strategies():
            name = s["name"]
            if strategy not in ("all", name):
                continue
            fn = _run_map.get(name)
            if fn:
                fn(limit, progress_callback)

        from data.results_db import list_strategies
        return {"strategies": list_strategies()}

    run_job(job_id, _run)
    return job_id


def _run_buffett(limit: int, progress_callback):
    from data.results_db import save_buffett_results, save_strategy_signals
    from scripts.compute_signals import compute_buffett

    progress_callback(1, 100, "Buffett running")
    results = compute_buffett(limit)
    save_buffett_results(results)
    signals = [{
        "symbol": r["symbol"], "name": r["name"], "industry": r["industry"],
        "score": r["score"],
        "signal": "buy" if ("通过" in r.get("verdict", "") or "✅" in r.get("verdict", "")) else "hold",
        "detail": {"verdict": r["verdict"], "safe_margin": r["safety_margin"], "roe": r["roe"]},
    } for r in results]
    save_strategy_signals("buffett", signals)
    progress_callback(100, 100, "Buffett done")


def _run_multifactor(limit: int, progress_callback):
    from data.results_db import save_strategy_signals
    from scripts.compute_signals import compute_multifactor

    progress_callback(1, 100, "Multifactor running")
    results = compute_multifactor(limit)
    save_strategy_signals("multifactor", results)
    progress_callback(100, 100, "Multifactor done")


def _run_cybernetic(limit: int, progress_callback):
    from data.results_db import save_strategy_signals
    from scripts.compute_signals import compute_cybernetic

    progress_callback(1, 100, "Cybernetic running")
    results = compute_cybernetic(limit)
    save_strategy_signals("cybernetic", results)
    progress_callback(100, 100, "Cybernetic done")


def _run_ml_lgbm(limit: int, progress_callback):
    from data.results_db import save_strategy_signals
    from signals.ml_signals import compute_ml_signals

    progress_callback(1, 100, "ML running")
    results = compute_ml_signals(limit=limit)
    save_strategy_signals("ml_lgbm", results)
    progress_callback(100, 100, "ML done")
