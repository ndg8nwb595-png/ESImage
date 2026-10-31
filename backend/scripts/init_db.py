"""建表脚本：幂等创建登录链路所需的 6 张表。

用法（在 backend/ 目录）：
    .venv/Scripts/python.exe scripts/init_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows 控制台默认 GBK，统一改为 UTF-8，避免中文日志乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# 允许以 `python scripts/init_db.py` 方式运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models  # noqa: F401  确保模型已注册到 Base.metadata
from app.core.database import Base, engine


def init_db() -> None:
    """创建所有表；已存在的表不会被修改。"""
    print("[建表] 开始创建数据表……")
    Base.metadata.create_all(bind=engine)
    print("[建表] 完成。")


if __name__ == "__main__":
    init_db()
