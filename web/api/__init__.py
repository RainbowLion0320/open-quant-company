"""
Astrolabe Quant API v2 — FastAPI 应用工厂

模块化设计:
  web/api/
    __main__.py  → 启动入口 (python -m web.api)
    __init__.py  → 应用工厂 create_app()
    routes/      → 10个业务路由模块
    models.py    → Pydantic 类型
    jobs.py      → 异步任务队列
    ws.py        → WebSocket
    errors.py    → 错误处理
"""
