"""部署与运维路由：双健康探针 + SSE 演示探针。

- `GET /api/health`：11 号 §8.3 裸结构，供容器/网关探活。
- `GET /api/v1/health`：9 号统一响应，与裸探针共用同一检测逻辑。
- `GET /api/v1/sessions/_probe/stream`：仅非生产注册。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.context import request_id_var
from app.modules.ops.health import run_health_checks
from app.modules.ops.stream import sse_probe_stream

logger = logging.getLogger("esimage.ops")

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


@router.get("/api/health")
def health_bare() -> JSONResponse:
    checks = run_health_checks()
    degraded = any(value == "error" for value in checks.values())
    status = "degraded" if degraded else "ok"
    logger.info(
        "health check completed",
        extra={"extra_fields": {"status": status, "checks": checks}},
    )
    return JSONResponse(
        status_code=503 if degraded else 200,
        content={"status": status, "checks": checks},
        headers=_NO_STORE,
    )


@router.get("/api/v1/health")
def health_v1() -> JSONResponse:
    checks = run_health_checks()
    degraded = any(value == "error" for value in checks.values())
    status = "degraded" if degraded else "ok"
    if degraded:
        return JSONResponse(
            status_code=503,
            content={
                "code": 50001,
                "message": "服务依赖不可用",
                "data": {"status": "degraded", "checks": checks},
            },
            headers=_NO_STORE,
        )
    return JSONResponse(
        status_code=200,
        content={"code": 0, "message": "ok", "data": {"status": "ok", "checks": checks}},
        headers=_NO_STORE,
    )


if settings.APP_ENV != "production":

    @router.get("/api/v1/sessions/_probe/stream")
    def sse_probe():
        return sse_probe_stream(request_id_var.get() or "")
