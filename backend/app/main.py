"""FastAPI 应用入口。"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.response import ApiError, error_body
from app.modules.auth.router import router as auth_router
from app.modules.workspace.router import router as workspace_router

logger = logging.getLogger("esimage")

app = FastAPI(title="ESImage API", version="0.1.0")

# 本地联调默认走 Vite 代理；同时允许直连开发服务器
_default_origins = "http://localhost:5173,http://127.0.0.1:5173"
_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", _default_origins).split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")


@app.exception_handler(ApiError)
async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    """业务异常 -> 统一响应。"""
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message),
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """请求体/查询参数校验失败 -> 400 + 1xxx。"""
    errors = exc.errors()
    missing = any(error.get("type") == "missing" for error in errors)
    field = ""
    if errors:
        loc = errors[0].get("loc") or ()
        field = str(loc[-1]) if loc else ""

    # 工作台接口的关键字段按接口文档返回明确文案
    if field == "product_name":
        return JSONResponse(status_code=400, content=error_body(10002, "请先填写商品名称"))
    if field == "content":
        return JSONResponse(status_code=400, content=error_body(10002, "请输入内容"))
    if field == "file":
        return JSONResponse(status_code=400, content=error_body(10002, "请选择要上传的图片"))
    if field in ("width", "height"):
        return JSONResponse(status_code=400, content=error_body(10003, "宽高需为正整数"))

    if missing:
        return JSONResponse(status_code=400, content=error_body(10002, "缺少必填参数"))
    return JSONResponse(status_code=400, content=error_body(10003, "参数格式错误"))


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """数据库异常 -> 500 + 50002（接口文档 §4 错误码表）。"""
    logger.exception("数据库异常: %s", exc)
    return JSONResponse(status_code=500, content=error_body(50002, "系统繁忙，请稍后重试"))


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """未捕获异常 -> 500 + 50001；不向客户端暴露内部细节。"""
    logger.exception("未处理的异常: %s", exc)
    return JSONResponse(status_code=500, content=error_body(50001, "系统繁忙，请稍后重试"))
