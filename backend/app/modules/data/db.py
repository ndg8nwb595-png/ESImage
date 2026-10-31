"""数据底座（10 号）独立引擎与会话。

使用本模块自己的连接串创建引擎，避免与 ``app.core.database`` 绑定的业务连接串
（以及其依赖的 ``JWT_SECRET``）耦合，使 ``esimage-data`` 可独立启动。
"""

from __future__ import annotations

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from app.modules.data.config import config


def create_data_engine(url: str | None = None) -> Engine:
    """创建数据底座引擎，并为每个连接设置会话时区。"""
    engine = create_engine(url or config.DATABASE_URL, pool_pre_ping=True, future=True)

    @event.listens_for(engine, "connect")
    def _set_timezone(dbapi_conn, _record) -> None:  # pragma: no cover - 运行时回调
        cursor = dbapi_conn.cursor()
        try:
            cursor.execute(f"SET TIME ZONE '{config.DATABASE_TIMEZONE}'")
        finally:
            cursor.close()

    return engine


engine = create_data_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def check_database(engine: Engine | None = None) -> dict[str, str]:
    """校验数据库版本、编码与时区，不满足时抛 :class:`RuntimeError`。

    返回 ``{"version": "16", "encoding": "UTF8", "timezone": "Asia/Shanghai"}``。
    """
    target = engine or globals()["engine"]
    with target.connect() as conn:
        version = conn.execute(text("SHOW server_version")).scalar()
        encoding = conn.execute(text("SHOW server_encoding")).scalar()
        timezone = conn.execute(text("SHOW timezone")).scalar()

    major = str(version).split(".")[0]
    problems: list[str] = []
    if major != "16":
        problems.append(f"PostgreSQL 主版本必须为 16，实际为 {version}")
    if str(encoding).upper() != "UTF8":
        problems.append(f"字符集必须为 UTF-8，实际为 {encoding}")
    if str(timezone) != config.DATABASE_TIMEZONE:
        problems.append(f"会话时区必须为 {config.DATABASE_TIMEZONE}，实际为 {timezone}")

    if problems:
        raise RuntimeError("；".join(problems))
    return {"version": major, "encoding": str(encoding).upper(), "timezone": str(timezone)}
