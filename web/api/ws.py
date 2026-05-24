"""WebSocket — 策略运行实时进度推送"""

import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("astrolabe_quant.ws")

# job_id -> set of WebSocket connections
_connections: dict[str, set[WebSocket]] = {}


async def ws_endpoint(websocket: WebSocket, job_id: str = None):
    """WebSocket 端点 — 订阅特定 job 的进度"""
    await websocket.accept()

    if job_id:
        if job_id not in _connections:
            _connections[job_id] = set()
        _connections[job_id].add(websocket)
        logger.info(f"WS connected: job={job_id}, total={len(_connections[job_id])}")

    try:
        while True:
            # 轮询任务状态并推送，避免后台线程跨 event loop 调 broadcast。
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                if job_id:
                    from web.api.jobs import get_job
                    job = get_job(job_id)
                    if job:
                        await websocket.send_text(json.dumps({
                            "job_id": job_id,
                            "status": job.get("status"),
                            "progress": job.get("progress", 0),
                            "message": job.get("message", ""),
                        }))
                        if job.get("status") in ("done", "error"):
                            break
    except WebSocketDisconnect:
        pass
    finally:
        if job_id and job_id in _connections:
            _connections[job_id].discard(websocket)
            if not _connections[job_id]:
                del _connections[job_id]
