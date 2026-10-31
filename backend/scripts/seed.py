"""幂等种子脚本（CLI）。

用法（在 backend/ 目录）：
    .venv/Scripts/python.exe scripts/seed.py

规则：已存在的数据跳过，不覆盖（包括密码与账号状态）。
演示账号只用于本地，部署到共享环境前必须删除或改密。
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows 控制台默认 GBK，统一改为 UTF-8，避免中文日志乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models  # noqa: F401  确保模型已注册
from app.core.database import Base, SessionLocal, engine
from app.modules.admin.seed import seed_config
from app.modules.admin.seed_content import seed_admin_content
from app.modules.auth.seed import seed
from app.modules.history.seed import seed_history


def main() -> None:
    print("[种子] 开始写入种子数据……")
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
        seed_config(db)
        # 历史作品最小 demo 夹具；重复执行时按 client_request_id 跳过
        seed_history(db)
        # 7 号管理后台内容夹具；demo_user / demo_user2 / demo_super
        seed_admin_content(db)
    print("[种子] 完成。")


if __name__ == "__main__":
    main()
