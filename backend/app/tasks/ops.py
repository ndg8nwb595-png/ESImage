"""演示专用运维任务：`ops.selftest`（仅 `APP_ENV != production` 注册）。

用途：验证 Worker 可执行、队列连通、`request_id` 从 HTTP/任务头透传到 Worker 日志。
"""

from __future__ import annotations

import logging
import time
import uuid

from app.celery_app import celery_app
from app.core.config import settings
from app.core.context import request_id_var

logger = logging.getLogger("esimage.worker.ops")


def selftest(request_id: str | None = None, delay_ms: int = 0) -> dict:
    """纯函数实现，便于单测；设置 request_id 上下文并记录开始/结束/耗时。"""
    rid = request_id if isinstance(request_id, str) and request_id else str(uuid.uuid4())
    delay_ms = int(delay_ms or 0)
    token = request_id_var.set(rid)
    started = time.monotonic()
    try:
        logger.info(
            "ops.selftest start",
            extra={"extra_fields": {"request_id": rid, "delay_ms": delay_ms}},
        )
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
        duration_ms = round((time.monotonic() - started) * 1000)
        logger.info(
            "ops.selftest done",
            extra={"extra_fields": {"request_id": rid, "duration_ms": duration_ms}},
        )
        return {"status": "ok", "request_id": rid, "duration_ms": duration_ms}
    finally:
        request_id_var.reset(token)


if settings.APP_ENV != "production":

    @celery_app.task(name="ops.selftest", bind=True)
    def ops_selftest(self, request_id: str | None = None, delay_ms: int = 0) -> dict:
        # 后端入队时把当前请求 ID 写入任务头 `request_id`；这里也兼容 kwargs 传入
        headers: dict = {}
        request = getattr(self, "request", None)
        if request is not None:
            raw = getattr(request, "headers", None)
            if raw:
                try:
                    headers = dict(raw)
                except (TypeError, ValueError):
                    headers = {}
        rid = request_id or headers.get("request_id")
        return selftest(request_id=rid, delay_ms=delay_ms)
