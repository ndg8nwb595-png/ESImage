"""应用配置。

所有敏感配置均从环境变量读取；本地通过 backend/.env 注入（该文件不入库）。
"""

from __future__ import annotations

import base64
import binascii
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

        # 历史作品归档原件读取超时（秒）；超时按「文件归档中」处理
        self.ARCHIVE_READ_TIMEOUT_SECONDS = float(
            os.getenv("ARCHIVE_READ_TIMEOUT_SECONDS", "60")
        )
        # 7 号管理后台概览四卡缓存 TTL（秒）
        self.DASHBOARD_CACHE_TTL_SECONDS = int(
            os.getenv("DASHBOARD_CACHE_TTL_SECONDS", "60")
        )

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

        # 模型配置 API Key 的 AES-256-GCM 密钥：base64 编码的 32 字节
        # 8 号接口文档使用 MODEL_CONFIG_ENCRYPTION_KEY；
        # 11 号部署模板使用 ENCRYPTION_KEY，二者含义相同，优先前者、兼容后者。
        # 缺失或长度不符时应用启动失败，避免写入不可解密的数据。
        self.MODEL_CONFIG_ENCRYPTION_KEY: str = (
            os.getenv("MODEL_CONFIG_ENCRYPTION_KEY", "").strip()
            or os.getenv("ENCRYPTION_KEY", "").strip()
        )

        # 4 号生图任务：豆包模型配置。
        # Key 只从环境变量读取，不落库；ARK_* 是 3/4 号共享命名，DOUBAO_* 可覆盖。
        self.DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "").strip() or self.ARK_API_KEY
        self.DOUBAO_BASE_URL = (
            os.getenv("DOUBAO_BASE_URL", "").strip() or self.ARK_BASE_URL
        )
        self.DOUBAO_TEXT_MODEL = (
            os.getenv("DOUBAO_TEXT_MODEL", "").strip() or self.ARK_TEXT_MODEL
        )
        self.DOUBAO_IMAGE_MODEL = os.getenv(
            "DOUBAO_IMAGE_MODEL", "doubao-seedream-5-0-pro-260628"
        ).strip()
        self.DOUBAO_VISION_MODEL = os.getenv(
            "DOUBAO_VISION_MODEL", "doubao-seed-2-1-lite-260915"
        ).strip()
        self.DOUBAO_MODERATION_MODEL = os.getenv(
            "DOUBAO_MODERATION_MODEL", "doubao-seed-2-1-lite-260915"
        ).strip()

        # 整批超时秒数（默认 30 分钟；演示可用短阈值）
        self.BATCH_TIMEOUT_SECONDS = int(os.getenv("BATCH_TIMEOUT_SECONDS", "1800"))

        # 中文字体路径；为空时按内置候选列表查找
        self.FONT_PATH = os.getenv("FONT_PATH", "").strip()

        # 模型提供方：doubao（默认）/ fake（仅测试环境）
        self.GENERATION_MODEL_PROVIDER = os.getenv(
            "GENERATION_MODEL_PROVIDER", "doubao"
        ).strip()

        # 测试环境退避缩放系数；生产固定为 1
        self.AGENT_RETRY_BACKOFF_SCALE = float(
            os.getenv("AGENT_RETRY_BACKOFF_SCALE", "1")
        )

        # 故障注入（仅 APP_ENV=test 生效），逗号分隔：
        # core / image / quality / platform / composition / timeout / moderation
        self.GENERATION_FAULT_MODE = os.getenv("GENERATION_FAULT_MODE", "").strip()

        if not self.JWT_SECRET:
            raise RuntimeError(
                "缺少 JWT_SECRET 环境变量。请复制 backend/.env.example 为 backend/.env 并设置随机密钥。"
            )

        if not self.MODEL_CONFIG_ENCRYPTION_KEY:
            raise RuntimeError(
                "缺少 MODEL_CONFIG_ENCRYPTION_KEY（或 ENCRYPTION_KEY）环境变量。"
                "请设置 base64 编码的 32 字节密钥（例如 "
                "python -c \"import base64,os;print(base64.b64encode(os.urandom(32)).decode())\"）。"
            )
        try:
            key_bytes = base64.b64decode(self.MODEL_CONFIG_ENCRYPTION_KEY, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise RuntimeError(
                "MODEL_CONFIG_ENCRYPTION_KEY 不是合法的 base64；需为 base64 编码的 32 字节密钥。"
            ) from exc
        if len(key_bytes) != 32:
            raise RuntimeError(
                f"MODEL_CONFIG_ENCRYPTION_KEY 解码后为 {len(key_bytes)} 字节，需为 32 字节。"
            )


settings = Settings()
