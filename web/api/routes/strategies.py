"""策略中心路由 — 策略列表 / 信号 / 异步运行 / 进度"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from web.api.models import StrategyRunRequest, StrategyRunResponse, JobStatus, StrategyListResponse, StrategySignalsResponse
from web.api.errors import DataNotFoundError, InvalidParameterError, StrategyRunError

router = APIRouter(prefix="/api/strategies", tags=["Strategies"])


# ── 策略列表 ──────────────────────────────────────────────

@router.get("", response_model=StrategyListResponse)
async def list_strategies():
    """列出所有已计算策略及统计 + 策略注册表元数据"""
    from data.results_db import list_strategies as db_list
    from data.registry import get_enabled_strategies, ALLOWED_STATUSES

    strategies = db_list()
    registry = get_enabled_strategies()

    # Enrich with status metadata for frontend lifecycle display
    for s in registry:
        st = s.get("status", "candidate")
        s["status_rank"] = list(ALLOWED_STATUSES).index(st) if st in ALLOWED_STATUSES else 0

    return {
        "strategies": strategies,
        "registry": registry,
        "total": len(strategies),
        "statuses": list(ALLOWED_STATUSES),
    }


@router.get("/statuses")
async def get_strategy_statuses():
    """所有策略的当前生命周期状态."""
    from data.registry import get_enabled_strategies, status_label, ALLOWED_STATUSES
    registry = get_enabled_strategies()
    return {
        "strategies": [
            {
                "name": s["name"],
                "label": s["label"],
                "status": s.get("status", "candidate"),
                "status_label": status_label(s.get("status", "candidate")),
                "color": s["color"],
            }
            for s in registry
        ],
        "statuses": list(ALLOWED_STATUSES),
        "status_labels": {s: status_label(s) for s in ALLOWED_STATUSES},
        "status": "ok",
    }


# ── 启动策略运行 ──────────────────────────────────────────

@router.post("/run", response_model=StrategyRunResponse)
async def run_strategy(req: StrategyRunRequest):
    """异步启动策略扫描, 返回 job_id"""
    from web.api.jobs import run_strategy_async
    from data.registry import get_strategy, list_strategy_names

    valid = set(list_strategy_names()) | {"all"}
    if req.strategy not in valid:
        raise StrategyRunError(
            req.strategy,
            f"Invalid strategy. Choose from: {', '.join(sorted(valid))}",
        )

    job_id = await run_strategy_async(req.strategy, req.limit, req.params)
    return StrategyRunResponse(job_id=job_id, status="started")


# ── Job 状态 ──────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """获取异步任务状态"""
    from web.api.jobs import get_job

    job = get_job(job_id)
    if not job:
        raise DataNotFoundError("job", job_id)
    return JobStatus(**{k: job.get(k) for k in ("job_id", "status", "progress", "message", "result")})


# ── 策略信号 ──────────────────────────────────────────────

@router.get("/{name}", response_model=StrategySignalsResponse)
async def get_strategy_signals(
    name: str,
    sort: str = Query(default="score", description="score / symbol / name"),
    order: str = Query(default="desc", description="desc / asc"),
):
    """加载某策略的全部信号"""
    from data.registry import list_strategy_names
    from data.results_db import load_strategy_signals

    valid = set(list_strategy_names())
    if name not in valid:
        raise InvalidParameterError("strategy", name, f"Choose from: {', '.join(sorted(valid))}")

    signals = load_strategy_signals(name, sort=sort, order=order)
    if not signals:
        raise DataNotFoundError("strategy", name)
    return {
        "strategy": name,
        "total": len(signals),
        "buys": sum(1 for s in signals if s.get("signal") == "buy"),
        "signals": signals,
    }


# ── WebSocket 进度 ────────────────────────────────────────

@router.websocket("/ws/{job_id}")
async def ws_strategy_progress(websocket: WebSocket, job_id: str):
    """WebSocket — 订阅策略运行实时进度"""
    from web.api.ws import ws_endpoint

    await ws_endpoint(websocket, job_id=job_id)
