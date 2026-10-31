"""JSON 结构化日志。

backend / worker / beat 统一输出一行合法 JSON，至少包含
`time`、`level`、`module`、`request_id`、`user_id`、`message`；
同时写入 stdout 与按天轮转的文件日志（保留 `LOG_RETENTION_DAYS` 份，压缩为 `.gz`）。

禁止记录密码、JWT、API Key 等敏感信息由调用方保证，此处不做日志内容改写。
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.core.config import settings
from app.core.context import request_id_var, user_id_var


class JsonFormatter(logging.Formatter):
    """输出单行 JSON；额外字段通过 `extra={"extra_fields": {...}}` 传入。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "time": datetime.now(settings.TZ).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
            "message": record.getMessage(),
        }
        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            payload.update(extra_fields)
        if record.exc_info:
            payload["exc_type"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False, default=str)


def _gzip_rotator(source: str, dest: str) -> None:
    # dest 已由 namer 追加 .gz 后缀
    with open(source, "rb") as f_in, gzip.open(dest, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(source)


def _gzip_namer(name: str) -> str:
    return name + ".gz"


def configure_logging() -> logging.Logger:
    """配置 `esimage` logger（幂等：同一进程只注册一次 handler）。"""
    logger = logging.getLogger("esimage")
    if getattr(logger, "_esimage_configured", False):
        return logger

    logger.setLevel(settings.LOG_LEVEL.upper())
    logger.propagate = False

    formatter = JsonFormatter()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    try:
        log_dir = Path(settings.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        process = settings.ESIMAGE_PROCESS or "backend"
        file_handler = TimedRotatingFileHandler(
            log_dir / f"{process}.log",
            when="midnight",
            backupCount=settings.LOG_RETENTION_DAYS,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.namer = _gzip_namer
        file_handler.rotator = _gzip_rotator
        logger.addHandler(file_handler)
    except OSError:
        # 文件日志不可写时仍保留 stdout，避免启动失败
        pass

    logger._esimage_configured = True  # type: ignore[attr-defined]
    return logger
