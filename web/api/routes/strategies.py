"""策略中心路由 — 策略列表 / 信号 / 异步运行 / 进度"""

from fastapi import APIRouter, Query, WebSocket
from web.api.errors import DataNotFoundError
from web.api.schemas.strategy import (
    StrategyCatalogResponse,
    StrategyEvaluationSummaryResponse,
    StrategyEvidenceDetailResponse,
    StrategyEvidenceListResponse,
    StrategyListResponse,
    StrategyRunRequest,
    StrategyRunResponse,
    StrategySignalsResponse,
    JobStatus,
)
from web.api.services.strategies import (
    start_strategy_run,
    strategy_catalog_payload,
    strategy_evaluation_payload,
    strategy_evidence_detail_payload,
    strategy_evidence_list_payload,
    strategy_governance_payload,
    strategy_list_payload,
    strategy_signals_payload,
    strategy_status_payload,
)

router = APIRouter(prefix="/api/strategies", tags=["Strategies"])


# ── 策略列表 ──────────────────────────────────────────────

@router.get("", response_model=StrategyListResponse)
async def list_strategies():
    """列出所有已计算策略及统计 + 策略注册表元数据"""
    return strategy_list_payload()


@router.get("/statuses")
async def get_strategy_statuses():
    """所有策略的当前生命周期状态."""
    return strategy_status_payload()


@router.get("/governance")
async def get_strategy_governance():
    """Return strategy role layering and promotion gate definitions."""
    return strategy_governance_payload()


@router.get("/catalog", response_model=StrategyCatalogResponse)
async def get_strategy_catalog():
    """Return the strategy catalog contract used by research and UI surfaces."""
    return strategy_catalog_payload()


@router.get("/evaluation", response_model=StrategyEvaluationSummaryResponse)
async def get_strategy_evaluation_summary():
    """Return evaluation evidence requirements for candidate promotion."""
    return strategy_evaluation_payload()


# ── 启动策略运行 ──────────────────────────────────────────

@router.post("/run", response_model=StrategyRunResponse)
async def run_strategy(req: StrategyRunRequest):
    """异步启动策略扫描, 返回 job_id"""
    job_id = await start_strategy_run(req.strategy, req.limit, req.params, mode=req.mode)
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


# ── 策略证据 ──────────────────────────────────────────────

@router.get("/evidence", response_model=StrategyEvidenceListResponse)
async def list_strategy_evidence():
    """List all strategy evidence artifacts."""
    return strategy_evidence_list_payload()


@router.get("/evidence/{strategy}", response_model=StrategyEvidenceDetailResponse)
async def get_strategy_evidence(strategy: str):
    """Load a single strategy's evidence artifact."""
    return strategy_evidence_detail_payload(strategy)


# ── 策略信号 ──────────────────────────────────────────────

@router.get("/{name}", response_model=StrategySignalsResponse)
async def get_strategy_signals(
    name: str,
    sort: str = Query(default="score", description="score / symbol / name"),
    order: str = Query(default="desc", description="desc / asc"),
):
    """加载某策略的全部信号"""
    return strategy_signals_payload(name, sort=sort, order=order)


# ── WebSocket 进度 ────────────────────────────────────────

@router.websocket("/ws/{job_id}")
async def ws_strategy_progress(websocket: WebSocket, job_id: str):
    """WebSocket — 订阅策略运行实时进度"""
    from web.api.ws import ws_endpoint

    await ws_endpoint(websocket, job_id=job_id)
