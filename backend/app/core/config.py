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

        # 历史作品归档原件读取超时（秒）；超时按「文件归档中」处理
        self.ARCHIVE_READ_TIMEOUT_SECONDS = float(
            os.getenv("ARCHIVE_READ_TIMEOUT_SECONDS", "60")
        )

        if not self.JWT_SECRET:
            raise RuntimeError(
                "缺少 JWT_SECRET 环境变量。请复制 backend/.env.example 为 backend/.env 并设置随机密钥。"
            )


settings = Settings()
