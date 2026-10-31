"""迁移与种子入口（Compose `migrate` 一次性服务）。

等价于「正向迁移 + 幂等种子 + 初始超管」。当前仓库使用 SQLAlchemy
`create_all` 建表（与 init_db.py / seed.py 一致），暂无 Alembic 版本目录；
本脚本保持该方式，避免重复实现两套建表路径。

退出码：0 成功；1 配置/迁移失败（中文原因输出到 stderr）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows 控制台默认 GBK，统一改为 UTF-8，避免中文日志乱码
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# 允许以 `python scripts/migrate.py` 方式运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models  # noqa: F401  确保模型已注册
from app.core.database import Base, SessionLocal, engine
from app.modules.admin.seed import seed_config
from app.modules.auth.seed import seed
from app.modules.ops.seed import InitialAdminConfigError, seed_initial_admin, validate_initial_admin


def main() -> int:
    # 先校验初始超管配置，避免在数据库已变更后才因密码缺失失败
    try:
        validate_initial_admin()
    except InitialAdminConfigError as exc:
        print(f"[迁移] 失败：{exc}", file=sys.stderr)
        return 1

    print("[迁移] 创建/更新数据表……")
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed(db)
        seed_config(db)
        seed_initial_admin(db)
        db.commit()

    print("[迁移] 完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
