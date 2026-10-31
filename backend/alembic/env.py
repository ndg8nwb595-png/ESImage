"""Alembic 迁移环境（10 号数据底座）。

迁移脚本为手写、可正反向执行；``target_metadata`` 置空，避免依赖业务模型
（因此 ``esimage-data`` 无需 ``JWT_SECRET`` 即可迁移）。
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 连接串优先级：显式传入的 main option > 环境变量 > 默认
_url = config.get_main_option("sqlalchemy.url") or os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://esimage:esimage@127.0.0.1:55433/esimage_data",
)
config.set_main_option("sqlalchemy.url", _url)

# 手写迁移，不需要 autogenerate，故不绑定业务 metadata
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=_url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
