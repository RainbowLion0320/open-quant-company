"""系统活动监视器 — SQLite 时序库 + 历史趋势"""
from fastapi import APIRouter, Query

from web.api.errors import InvalidParameterError
from web.api.schemas.system import CronJobsResponse, SystemHealthResponse
from web.api.services.system_data_health import (
    db_health_payload,
    repair_status_payload,
    repairable_tables as _repairable_tables,
    start_repair_job,
)
from web.api.services.system_integrations import (
    api_health_payload,
    cron_jobs_payload,
)
from web.api.services.system_monitor import (
    llm_usage_payload,
    system_history_payload,
    system_monitor_payload,
)
from web.api.services.system_data_ops import (
    audit_history_payload,
    backfill_history_payload,
    contracts_payload,
    last_backfill_payload,
    provider_health_payload,
    quality_gate_payload,
)
from web.api.services.system_orders import order_lifecycle_payload, order_trace_payload

router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/monitor")
async def system_monitor():
    """当前快照 (读最新一行 SQLite)"""
    return system_monitor_payload()


@router.get("/history")
async def system_history(hours: int = Query(default=24, ge=1, le=720)):
    """历史趋势数据 — CPU/内存/Token 时间序列"""
    return system_history_payload(hours)

@router.get("/llm-usage")
async def llm_usage(provider: str | None = Query(default=None)):
    """Generic LLM provider balance and project-local API response usage ledger."""
    return llm_usage_payload(provider=provider)


@router.get("/db-health")
async def db_health():
    """数据库健康检查结果 — 最新一次扫描"""
    return db_health_payload()


@router.post("/db-health/repair/{table_name}")
async def repair_table(table_name: str):
    """触发单表数据修复 (后台异步)"""
    if table_name not in _repairable_tables():
        raise InvalidParameterError("table_name", table_name, "Not a repairable table")
    return start_repair_job(table_name)


@router.get("/db-health/repair-status/{job_id}")
async def repair_status(job_id: str):
    """查询修复进度"""
    return repair_status_payload(job_id)


@router.get("/api-health", response_model=SystemHealthResponse)
async def api_health():
    """检查各 API 配置健康状态 (不含 token 值)。"""
    return api_health_payload()


@router.get("/cron-jobs", response_model=CronJobsResponse)
async def cron_jobs():
    """Cron job 状态 (读取 ~/.hermes/cron/jobs.json)"""
    return cron_jobs_payload()


@router.get("/quality-gate")
async def quality_gate(dimension: str = Query(default="", description="Check a single dimension (empty = all critical)")):
    """数据质量门禁 — freshness SLA / completeness / consistency."""
    return quality_gate_payload(dimension)


@router.get("/runs")
async def list_runs(limit: int = Query(default=20, ge=1, le=100), run_type: str = Query(default="", description="workflow / tournament / train")):
    """列出最近的实验 runs (workflow / tournament / train)"""
    from research.runs import list_runs as _list_runs
    runs = _list_runs(limit=limit, run_type=run_type)
    return {"runs": runs, "total": len(runs)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """获取单个 run 的详细信息"""
    from research.runs import get_run as _get_run
    from web.api.errors import DataNotFoundError
    run = _get_run(run_id)
    if run is None:
        raise DataNotFoundError("run", run_id)
    return run


# ── P1-7: Order Lifecycle ──


@router.get("/orders")
async def get_orders(
    date: str = Query(default="", description="Filter by date YYYY-MM-DD"),
    symbol: str = Query(default="", description="Filter by stock code"),
    status: str = Query(default="", description="Filter by status: pending/partial_filled/filled/rejected/cancelled/expired"),
    limit: int = Query(default=50, ge=1, le=500),
):
    """查询订单生命周期事件 — 从 EventLedger 读取。

    支持按日期、股票代码、状态过滤。
    返回订单列表，每个订单包含完整的状态变更历史。
    """
    return order_lifecycle_payload(date=date, symbol=symbol, status=status, limit=limit)


@router.get("/orders/{order_id}/trace")
async def trace_order(order_id: str):
    """追溯单个订单的完整生命周期链。

    从订单创建 → 部分成交 → 完全成交 → NAV 快照,
    每一步都有 event_id、timestamp 和 parent 关联。
    可以反向追溯到触发该订单的信号。
    """
    return order_trace_payload(order_id)


# ── P1-8: Backfill & Provider Health ──


@router.get("/backfill")
async def get_backfill_history(
    dimension: str = Query(default="", description="Filter by dimension key"),
    status: str = Query(default="", description="Filter: done/failed/running"),
    limit: int = Query(default=20, ge=1, le=200),
):
    """查询数据补数/修复历史 — 从 BackfillLedger 读取。

    每次 repair_table.py 执行都会在此留下记录，
    可追溯每个维度的补数时间、范围、结果。
    """
    return backfill_history_payload(dimension=dimension, status=status, limit=limit)


@router.get("/backfill/{dimension}/last")
async def get_last_backfill(dimension: str):
    """查询某个维度的最近一次补数记录。"""
    return last_backfill_payload(dimension)


@router.get("/providers/health")
async def get_provider_health():
    """各数据源的连接健康状态 — AKShare / Tushare。"""
    return provider_health_payload()


@router.get("/contracts")
async def get_contracts(dimension: str = Query(default="", description="Filter by dimension")):
    """数据维度契约列表 — schema/PK/PIT规则/sla。"""
    return contracts_payload(dimension)


# ── P1-11: Audit Log & Run Mode ──


@router.get("/audit")
async def get_audit_history(
    section: str = Query(default="", description="Filter by config section"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """查询配置变更审计日志 — 从 ConfigAuditLedger 读取。

    每次 PUT/PATCH /api/settings 都会记录变更:
    哪个 section, 哪些 key 变了, 来自哪个 IP, 在什么 run_mode 下。
    """
    return audit_history_payload(section=section, limit=limit)


@router.get("/mode")
async def get_system_mode():
    """当前系统运行模式 — research | paper | live。"""
    from web.api.auth import get_run_mode, get_api_key
    mode = get_run_mode()
    has_key = bool(get_api_key())
    return {
        "mode": mode,
        "has_api_key": has_key,
        "allows_settings_write": mode != "live",
        "allows_paper_trading": mode in ("research", "paper"),
        "readonly_sections": sorted({
            "live": ["all"],
            "paper": ["all except paper_trading"],
            "research": [],
        }.get(mode, [])),
        "status": "ok",
    }
