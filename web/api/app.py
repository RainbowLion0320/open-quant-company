"""
Astrolabe Quant API v2 -- Application Factory
"""

import os, sys
from pathlib import Path

for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(key, None)
os.environ["no_proxy"] = "eastmoney.com,10jqka.com.cn,sina.com.cn,qianlong.com,163.com,qq.com"

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from web.api.routes import market, strategies, stocks, portfolio, signals, settings, backtest, system, codegraph, sectors, pipeline, assets
from web.api.errors import register_error_handlers
from web.api.auth import AuthMiddleware
from web.api.version import get_project_version


def create_app() -> FastAPI:
    version = get_project_version()
    app = FastAPI(
        title="Astrolabe Quant API",
        version=version,
        description="星盘 / Astrolabe Quant OS — 个人量化研究与执行操作系统",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8501",
            "http://127.0.0.1:8501",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Key auth (after CORS so preflight requests skip auth)
    app.add_middleware(AuthMiddleware)

    app.include_router(market.router)
    app.include_router(strategies.router)
    app.include_router(stocks.router)
    app.include_router(portfolio.router)
    app.include_router(signals.router)
    app.include_router(settings.router)
    app.include_router(backtest.router)
    app.include_router(system.router)
    app.include_router(codegraph.router)
    app.include_router(sectors.router)
    app.include_router(pipeline.router)
    app.include_router(assets.router)

    register_error_handlers(app)

    @app.get("/api/health")
    async def health():
        from data.storage.results_db import get_buffett_meta, list_strategies
        from data.storage.db import get_backend
        db_locked = False
        meta = {}
        strategies_count = 0
        try:
            meta = get_buffett_meta()
            strategies_count = len(list_strategies())
        except Exception as e:
            db_locked = "lock" in str(e).lower() or "conflict" in str(e).lower()
        return {
            "status": "degraded" if db_locked else "ok",
            "db_locked": db_locked,
            "backend": get_backend(),
            "data_updated": meta.get("last_scan", "") if not db_locked else "数据库被占用",
            "stocks_scanned": meta.get("total", 0) if not db_locked else 0,
            "strategies": strategies_count,
            "version": version,
        }

    # 静态文件 (前端)
    static_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if static_dir.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        
        # SPA fallback: 非 API 路径回退到 index.html
        from fastapi.responses import FileResponse
        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not Found")
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(index, media_type="text/html")
            return {"detail": "Not Found"}

    return app
