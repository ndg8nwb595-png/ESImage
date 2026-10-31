"""Celery 应用（worker / beat 复用同一 backend 镜像）。

- broker 与结果后端均来自 `REDIS_URL`。
- 时区 `Asia/Shanghai`；调度表本 demo 为空，不注册业务定时任务。
- worker 并发数由 Compose 的 `WORKER_CONCURRENCY` 传入（见 docker-compose.yml）。
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings
from app.core.logging import configure_logging

# worker / beat 进程日志：文件名由 ESIMAGE_PROCESS 决定
configure_logging()

celery_app = Celery("esimage", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_default_queue="esimage",
    worker_max_tasks_per_child=100,
    worker_hijack_root_logger=False,
    beat_schedule={},
)

# 导入任务模块以注册任务（ops.selftest 仅在非生产注册）
import app.tasks.ops  # noqa: E402,F401
