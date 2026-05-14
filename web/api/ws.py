"""WebSocket — 策略运行实时进度推送"""

import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger("quant-agent.ws")

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
            # 保持连接，等待客户端消息 (用于心跳)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        if job_id and job_id in _connections:
            _connections[job_id].discard(websocket)
            if not _connections[job_id]:
                del _connections[job_id]


async def broadcast_progress(job_id: str, progress: int, message: str):
    """向订阅该 job 的所有 WebSocket 广播进度"""
    if job_id not in _connections:
        return

    payload = json.dumps({
        "job_id": job_id,
        "progress": progress,
        "message": message,
    })

    dead = set()
    for ws in _connections[job_id]:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)

    for ws in dead:
        _connections[job_id].discard(ws)
