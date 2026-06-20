"""统一错误处理 — 生产级日志 + 类型化错误响应"""

import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime

logger = logging.getLogger("astrolabe_quant.api")


class QuantError(Exception):
    """基础业务异常"""
    def __init__(self, message: str, detail: str = "", status_code: int = 500):
        self.message = message
        self.detail = detail
        self.status_code = status_code


class DataNotFoundError(QuantError):
    def __init__(self, resource: str, identifier: str = ""):
        msg = f"{resource} not found"
        if identifier:
            msg += f": {identifier}"
        super().__init__(msg, status_code=404)


class StrategyRunError(QuantError):
    def __init__(self, strategy: str, detail: str = ""):
        super().__init__(f"Strategy run failed: {strategy}", detail, status_code=500)


class InvalidParameterError(QuantError):
    def __init__(self, param: str, value: str = "", reason: str = ""):
        msg = f"Invalid parameter: {param}"
        if value:
            msg += f" = {value}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg, status_code=400)


async def quant_error_handler(request: Request, exc: QuantError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "detail": exc.detail,
            "timestamp": datetime.now().isoformat(),
        }
    )


async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled API error")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": None,
            "timestamp": datetime.now().isoformat(),
        }
    )


def register_error_handlers(app):
    from fastapi import HTTPException

    @app.exception_handler(QuantError)
    async def _(request, exc):
        return await quant_error_handler(request, exc)

    @app.exception_handler(HTTPException)
    async def _(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "timestamp": datetime.now().isoformat(),
            }
        )

    @app.exception_handler(Exception)
    async def _(request, exc):
        return await unhandled_error_handler(request, exc)
