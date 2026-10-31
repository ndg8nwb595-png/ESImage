"""数据底座（10 号）运行期配置。

独立于 ``app.core.config``：直接从环境变量读取，不依赖 ``JWT_SECRET``，
使 ``esimage-data`` 命令可在未配置业务密钥的环境下独立运行。
"""

from __future__ import annotations

import os
from pathlib import Path

# backend/ 目录（modules -> data -> app -> backend）
_BASE_DIR = Path(__file__).resolve().parents[3]


class DataConfig:
    """数据底座配置。"""

    def __init__(self) -> None:
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://esimage:esimage@127.0.0.1:55433/esimage_data",
        )
        self.DATABASE_TIMEZONE: str = os.getenv("DATABASE_TIMEZONE", "Asia/Shanghai")

        self.STORAGE_BACKEND: str = os.getenv("STORAGE_BACKEND", "local").strip().lower()
        storage_root = Path(os.getenv("STORAGE_ROOT", "storage"))
        self.STORAGE_ROOT: Path = (
            storage_root if storage_root.is_absolute() else _BASE_DIR / storage_root
        )

        # 归档保留期（天）；正式实现固定 1825，demo 可调小以缩短验证时间
        self.ARCHIVE_RETENTION_DAYS: int = int(os.getenv("ARCHIVE_RETENTION_DAYS", "1825"))

        self.MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "")
        self.MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "")
        self.MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "")
        self.MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "esimage")
        self.MINIO_SECURE: bool = os.getenv("MINIO_SECURE", "false").strip().lower() in (
            "1", "true", "yes", "on",
        )

        # 首个超管（init-super-admin / bootstrap 必填，无代码内默认值）
        self.INITIAL_SUPER_ADMIN_USERNAME: str = os.getenv(
            "INITIAL_SUPER_ADMIN_USERNAME", ""
        )
        self.INITIAL_SUPER_ADMIN_PASSWORD: str = os.getenv(
            "INITIAL_SUPER_ADMIN_PASSWORD", ""
        )


config = DataConfig()
