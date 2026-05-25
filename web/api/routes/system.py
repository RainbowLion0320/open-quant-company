"""系统活动监视器 — SQLite 时序库 + 历史趋势"""
from fastapi import APIRouter, Query

from web.api.errors import InvalidParameterError
from web.api.services.system_data_health import (
    db_health_payload,
    repair_status_payload,
    repairable_tables as _repairable_tables,
    start_repair_job,
)
from web.api.services.system_integrations import (
    api_health_payload,
    cron_jobs_payload,
    service_status_payload,
)
from web.api.services.system_monitor import (
    deepseek_usage_payload,
    system_history_payload,
    system_monitor_payload,
)

router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/monitor")
async def system_monitor():
    """当前快照 (读最新一行 SQLite)"""
    return system_monitor_payload()


@router.get("/history")
async def system_history(hours: int = Query(default=24, ge=1, le=720)):
    """历史趋势数据 — CPU/内存/Token 时间序列"""
    return system_history_payload(hours)

@router.get("/deepseek-usage")
async def deepseek_usage():
    """DeepSeek daily token/cost summary from Parquet."""
    return deepseek_usage_payload()


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


@router.get("/api-health")
async def api_health():
    """检查各 API 配置健康状态 (不含 token 值)。"""
    return api_health_payload()


@router.get("/cron-jobs")
async def cron_jobs():
    """Cron job 状态 (读取 ~/.hermes/cron/jobs.json)"""
    return cron_jobs_payload()


@router.get("/service-status")
async def service_status():
    """CDP / MCP / Cookie 状态检查"""
    return service_status_payload()


@router.get("/quality-gate")
async def quality_gate(dimension: str = Query(default="", description="Check a single dimension (empty = all critical)")):
    """数据质量门禁 — freshness SLA / completeness / consistency."""
    from data.quality import DataQualityGate
    gate = DataQualityGate()
    if dimension:
        report = gate.check_dimension(dimension)
        return {
            "dimension": report.dimension,
            "label": report.label,
            "status": report.status,
            "health_score": report.health_score,
            "freshness_days": report.freshness_days,
            "sla_days": report.sla_days,
            "row_count": report.row_count,
            "null_pct": report.null_pct,
            "date_min": report.date_min,
            "date_max": report.date_max,
            "issues": report.issues,
        }
    return gate.summary_report()


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
    from broker.ledger import EventLedger, EventType

    ledger = EventLedger()
    all_events = ledger.replay()

    if not all_events:
        return {"orders": [], "total": 0, "status": "ok"}

    # Group events by order_id
    orders: dict[str, dict] = {}
    for e in all_events:
        if date and e.run_date != date:
            continue
        if symbol and e.symbol != symbol:
            continue

        oid = e.order_id
        if oid not in orders:
            orders[oid] = {
                "order_id": oid,
                "symbol": e.symbol,
                "strategy": e.strategy,
                "run_date": e.run_date,
                "events": [],
                "current_state": "unknown",
                "transitions": [],
            }

        orders[oid]["events"].append({
            "event_id": e.event_id,
            "event_type": e.event_type.value,
            "timestamp": e.timestamp,
            "sequence": e.sequence,
            "payload": e.payload,
        })

        # Track state transitions
        from_s = e.payload.get("from_state", "")
        to_s = e.payload.get("to_state", e.event_type.value)
        if from_s and to_s:
            orders[oid]["transitions"].append({
                "timestamp": e.timestamp,
                "from_state": from_s,
                "to_state": to_s,
                "reason": e.payload.get("reason", ""),
            })
        orders[oid]["current_state"] = to_s

    # Apply status filter after grouping
    result = list(orders.values())
    if status:
        result = [o for o in result if o["current_state"] == status]

    # Sort by most recent first, limit
    result.sort(key=lambda o: o.get("run_date", ""), reverse=True)
    result = result[:limit]

    return {
        "orders": result,
        "total": len(result),
        "status": "ok",
    }


@router.get("/orders/{order_id}/trace")
async def trace_order(order_id: str):
    """追溯单个订单的完整生命周期链。

    从订单创建 → 部分成交 → 完全成交 → NAV 快照,
    每一步都有 event_id、timestamp 和 parent 关联。
    可以反向追溯到触发该订单的信号。
    """
    from broker.ledger import EventLedger, EventType

    ledger = EventLedger()
    trace = ledger.trace_order(order_id)

    if not trace["events"]:
        from web.api.errors import DataNotFoundError
        raise DataNotFoundError("order", order_id)

    # Enrich: find related NAV snapshots on the same date
    order_events = trace["events"]
    if order_events:
        run_date = order_events[0].run_date
        nav_events = ledger.events_by_type(EventType.NAV_SNAPSHOT, limit=200)
        related_nav = [
            {"event_id": e.event_id, "timestamp": e.timestamp, "payload": e.payload}
            for e in nav_events if e.run_date == run_date
        ]
    else:
        related_nav = []

    return {
        "order_id": order_id,
        "current_state": trace["current_state"],
        "transitions": trace["transitions"],
        "signal_info": trace["signal_info"],
        "events": [
            {
                "event_id": e.event_id,
                "event_type": e.event_type.value,
                "timestamp": e.timestamp,
                "sequence": e.sequence,
                "parent_event_id": e.parent_event_id,
                "symbol": e.symbol,
                "strategy": e.strategy,
                "payload": e.payload,
            }
            for e in order_events
        ],
        "related_nav": related_nav,
        "status": "ok",
    }


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
    from data.backfill import BackfillLedger
    ledger = BackfillLedger()

    entries = ledger.history(dimension=dimension, status=status, limit=limit)
    summary = ledger.summary()

    return {
        "entries": [
            {
                "run_id": e.run_id,
                "dimension": e.dimension,
                "status": e.status,
                "date_start": e.date_start,
                "date_end": e.date_end,
                "rows_fetched": e.rows_fetched,
                "error": e.error,
                "retry_count": e.retry_count,
                "started_at": e.started_at,
                "completed_at": e.completed_at,
                "duration_seconds": e.duration_seconds,
                "triggered_by": e.triggered_by,
            }
            for e in entries
        ],
        "summary": summary,
        "total": len(entries),
        "status": "ok",
    }


@router.get("/backfill/{dimension}/last")
async def get_last_backfill(dimension: str):
    """查询某个维度的最近一次补数记录。"""
    from data.backfill import BackfillLedger
    ledger = BackfillLedger()

    last = ledger.last_run(dimension)
    last_ok = ledger.last_successful(dimension)

    return {
        "dimension": dimension,
        "last_run": {
            "run_id": last.run_id, "status": last.status,
            "started_at": last.started_at, "completed_at": last.completed_at,
            "rows_fetched": last.rows_fetched, "error": last.error,
        } if last else None,
        "last_successful": {
            "run_id": last_ok.run_id, "started_at": last_ok.started_at,
            "rows_fetched": last_ok.rows_fetched,
        } if last_ok else None,
        "status": "ok",
    }


@router.get("/providers/health")
async def get_provider_health():
    """各数据源的连接健康状态 — AKShare / Tushare。"""
    from data.provider import provider_health_report
    return {
        "providers": provider_health_report(),
        "status": "ok",
    }


@router.get("/contracts")
async def get_contracts(dimension: str = Query(default="", description="Filter by dimension")):
    """数据维度契约列表 — schema/PK/PIT规则/sla。"""
    from data.contract import list_contracts
    contracts = list_contracts()

    if dimension:
        contracts = [c for c in contracts if c.dimension == dimension]

    return {
        "contracts": [
            {
                "dimension": c.dimension,
                "schema_version": c.schema_version,
                "columns": c.columns,
                "primary_key": c.primary_key,
                "freq": c.freq,
                "sla_days": c.sla_days,
                "pit_rule": c.pit_rule,
                "owner": c.owner,
                "description": c.description,
                "migration_count": len(c.migrations),
            }
            for c in contracts
        ],
        "total": len(contracts),
        "status": "ok",
    }


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
    from data.audit import ConfigAuditLedger
    ledger = ConfigAuditLedger()

    entries = ledger.history(section=section, limit=limit)
    summary = ledger.summary()

    return {
        "entries": [
            {
                "change_id": e.change_id,
                "timestamp": e.timestamp,
                "section": e.section,
                "method": e.method,
                "changed_keys": e.changed_keys,
                "source_ip": e.source_ip,
                "run_mode": e.run_mode,
            }
            for e in entries
        ],
        "summary": summary,
        "total": len(entries),
        "status": "ok",
    }


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
