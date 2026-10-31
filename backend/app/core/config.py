"""应用配置。

所有敏感配置均从环境变量读取；本地通过 backend/.env 注入（该文件不入库）。
"""

from __future__ import annotations

import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# backend/ 目录（core -> app -> backend）
BASE_DIR = Path(__file__).resolve().parents[2]
# load_dotenv 默认不覆盖已存在的环境变量，便于 pytest 在导入前指定测试库
load_dotenv(BASE_DIR / ".env")


class Settings:
    """运行期配置。"""

    def __init__(self) -> None:
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://esimage:esimage@127.0.0.1:5432/esimage",
        )
        self.JWT_SECRET: str = os.getenv("JWT_SECRET", "")
        self.JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
        # 未勾选「记住我」：24 小时；勾选：7 天
        self.TOKEN_TTL_DEFAULT = timedelta(hours=24)
        self.TOKEN_TTL_REMEMBER = timedelta(days=7)
        # 接口时间统一为东八区
        self.TZ = timezone(timedelta(hours=8))

        # 最小 demo 的本地对象存储根目录（替代 MinIO）
        storage_root = Path(os.getenv("STORAGE_ROOT", "storage"))
        self.STORAGE_ROOT = storage_root if storage_root.is_absolute() else BASE_DIR / storage_root

        # 演示生成管线每个阶段的停顿秒数，便于前端观察阶段进度
        self.DEMO_PIPELINE_STAGE_DELAY = float(os.getenv("DEMO_PIPELINE_STAGE_DELAY", "0.15"))

        # 3 号 Agent 会话交互：消息超时阈值、上下文轮数与 SSE 心跳间隔
        self.CHAT_MESSAGE_TIMEOUT_SECONDS = int(
            os.getenv("CHAT_MESSAGE_TIMEOUT_SECONDS", "120")
        )
        self.CHAT_CONTEXT_ROUNDS = int(os.getenv("CHAT_CONTEXT_ROUNDS", "10"))
        self.SSE_HEARTBEAT_SECONDS = float(os.getenv("SSE_HEARTBEAT_SECONDS", "15"))

        # 豆包（火山方舟）文本模型；未配置 API Key 或显式开启演示桩时走确定性桩
        self.ARK_API_KEY: str = os.getenv("ARK_API_KEY", "") or os.getenv(
            "DOUBAO_API_KEY", ""
        )
        self.ARK_BASE_URL: str = os.getenv(
            "ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
        )
        self.ARK_TEXT_MODEL: str = os.getenv(
            "ARK_TEXT_MODEL", "doubao-seed-character-260628"
        )
        self.ARK_TIMEOUT_SECONDS: float = float(os.getenv("ARK_TIMEOUT_SECONDS", "60"))
        self.CHAT_USE_STUB: bool = os.getenv("CHAT_USE_STUB", "false").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

        # 11 号部署与运维：运行环境、依赖地址与调优
        self.APP_ENV: str = os.getenv("APP_ENV", "development")
        # 进程角色：backend / worker / beat，决定日志文件名
        self.ESIMAGE_PROCESS: str = os.getenv("ESIMAGE_PROCESS", "backend")
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        self.MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
        self.MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "esimage")
        self.MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "esimage")
        self.MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "esimage")
        self.MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self.LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_RETENTION_DAYS: int = int(os.getenv("LOG_RETENTION_DAYS", "90"))
        _log_dir = Path(os.getenv("LOG_DIR", "")) if os.getenv("LOG_DIR") else BASE_DIR / "logs"
        self.LOG_DIR = str(_log_dir)
        self.WORKER_CONCURRENCY: int = int(os.getenv("WORKER_CONCURRENCY", "4"))
        self.ADMIN_INITIAL_USERNAME: str = os.getenv("ADMIN_INITIAL_USERNAME", "")
        self.ADMIN_INITIAL_PASSWORD: str = os.getenv("ADMIN_INITIAL_PASSWORD", "")
        # 健康检查单项超时（秒）；三项并发，整体不超 5 秒
        self.HEALTH_CHECK_TIMEOUT: float = float(os.getenv("HEALTH_CHECK_TIMEOUT", "2"))

        if not self.JWT_SECRET:
            raise RuntimeError(
                "缺少 JWT_SECRET 环境变量。请复制 backend/.env.example 为 backend/.env 并设置随机密钥。"
            )


settings = Settings()
