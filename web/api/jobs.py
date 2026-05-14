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
    from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_SECTOR, FALLBACK_SECTOR, SYMBOL_NAME
    from data.financials import get_buffett_inputs
    from buffett.filters import buffett_filter as bf
    from data.results_db import save_buffett_results, save_strategy_signals

    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    results = []
    total = len(symbols)

    for i, sym in enumerate(symbols):
        try:
            ind = SYMBOL_INDUSTRY.get(sym, "待分类")
            sec = SYMBOL_SECTOR.get(sym, FALLBACK_SECTOR)
            inputs = get_buffett_inputs(sym, current_price=0, industry=ind)
            if not inputs or not inputs.get("roe_history"):
                continue

            r = bf(symbol=sym, name=SYMBOL_NAME.get(sym, sym), **inputs)
            passed = "通过" in r.verdict.value if hasattr(r.verdict, 'value') else False

            results.append({
                "symbol": r.symbol, "name": r.name,
                "industry": r.industry, "sector": r.sector,
                "verdict": r.verdict.value if hasattr(r.verdict, 'value') else str(r.verdict),
                "score": r.score,
                "roe": round(r.avg_roe_5y * 100, 1),
                "gross_margin": round(r.avg_gross_margin_5y * 100, 1) if r.avg_gross_margin_5y > 0 else None,
                "net_margin": round(r.avg_net_margin_5y * 100, 1) if r.avg_net_margin_5y > 0 else None,
                "de": round(r.debt_equity_ratio, 1),
                "safety_margin": round(r.safety_margin_pct * 100, 1),
                "dcf_value": round(r.dcf_value, 1),
                "current_price": 0,
            })
        except Exception:
            pass

        if (i + 1) % max(1, total // 10) == 0 or i == 0:
            progress_callback(i + 1, total, f"Buffett [{i+1}/{total}]")

    save_buffett_results(results)
    signals = [{
        "symbol": r["symbol"], "name": r["name"], "industry": r["industry"],
        "score": r["score"],
        "signal": "buy" if "通过" in r.get("verdict", "") else "hold",
        "detail": {"verdict": r["verdict"], "safe_margin": r["safety_margin"], "roe": r["roe"]},
    } for r in results]
    save_strategy_signals("buffett", signals)
    progress_callback(total, total, "Buffett done")


def _run_multifactor(limit: int, progress_callback):
    from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_NAME
    from data.financials import get_buffett_inputs
    from signals.multifactor import MultiFactorScorer
    from cybernetics.orchestrator import QuantOrchestrator
    from data.results_db import save_strategy_signals

    orch = QuantOrchestrator()
    try:
        snapshot = orch.detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, 'value') else str(snapshot.regime)
    except Exception:
        regime = "sideways"

    scorer = MultiFactorScorer(regime=regime)
    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    results = []
    total = len(symbols)

    for i, sym in enumerate(symbols):
        try:
            ind = SYMBOL_INDUSTRY.get(sym, "待分类")
            inputs = get_buffett_inputs(sym, current_price=0, industry=ind)
            if not inputs:
                continue

            roe_hist = inputs.get("roe_history", [])
            roe_5y = sum(roe_hist[-5:]) / max(1, len(roe_hist[-5:])) if roe_hist else 0

            factors = {
                "buffett_score": min(100, roe_5y * 500),
                "safety_margin": max(0, inputs.get("safety_margin_pct", 0) / 100),
                "roe_5y": roe_5y,
                "roe_trend": "flat",
                "momentum_1m": 0, "momentum_3m": 0, "volatility": 0.30,
                "sector": inputs.get("sector", ""),
            }
            score = scorer.score(factors)
            signal = "buy" if score >= 60 else "hold"

            results.append({
                "symbol": sym, "name": SYMBOL_NAME.get(sym, sym),
                "industry": ind, "score": round(score, 1), "signal": signal,
                "detail": {"regime": regime},
            })
        except Exception:
            pass

        if (i + 1) % max(1, total // 10) == 0 or i == 0:
            progress_callback(i + 1, total, f"Multifactor [{i+1}/{total}]")

    save_strategy_signals("multifactor", results)
    progress_callback(total, total, "Multifactor done")


def _run_cybernetic(limit: int, progress_callback):
    from data.symbols import CIRCLE_STOCKS, SYMBOL_INDUSTRY, SYMBOL_NAME, SYMBOL_SECTOR, FALLBACK_SECTOR
    from cybernetics.orchestrator import QuantOrchestrator
    from data.results_db import save_strategy_signals

    orch = QuantOrchestrator()
    try:
        snapshot = orch.detect()
        regime = snapshot.regime.value if hasattr(snapshot.regime, 'value') else str(snapshot.regime)
        params = orch.get_params()
    except Exception:
        regime = "sideways"
        params = {"position_pct": 0.15, "max_positions": 5, "stop_loss": -0.05}

    regime_sectors = {
        "bull": ["证券", "电子", "计算机", "电力设备", "国防军工"],
        "bear": ["银行", "公用事业", "交通运输", "食品饮料", "医药生物"],
        "sideways": ["银行", "公用事业", "煤炭", "石油石化", "建筑装饰"],
    }
    favored = regime_sectors.get(regime, regime_sectors["sideways"])

    symbols = list(CIRCLE_STOCKS)
    if limit and limit < len(symbols):
        symbols = symbols[:limit]

    results = []
    total = len(symbols)
    for i, sym in enumerate(symbols):
        ind = SYMBOL_INDUSTRY.get(sym, "待分类")
        sec = SYMBOL_SECTOR.get(sym, FALLBACK_SECTOR)
        score = 75.0 if ind in favored else 40.0
        signal = "buy" if ind in favored else "hold"
        results.append({
            "symbol": sym, "name": SYMBOL_NAME.get(sym, sym),
            "industry": ind, "score": score, "signal": signal,
            "detail": {"regime": regime, "favored_sectors": favored},
        })

        if (i + 1) % max(1, total // 10) == 0 or i == 0:
            progress_callback(i + 1, total, f"Cybernetic [{i+1}/{total}]")

    save_strategy_signals("cybernetic", results)
    progress_callback(total, total, "Cybernetic done")
