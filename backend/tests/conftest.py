"""pytest 全局夹具：测试数据库、种子数据与状态重置。"""

from __future__ import annotations

import os

# 必须在导入 app.* 之前覆盖环境变量，确保 engine 指向测试库
TEST_DB_HOST = os.getenv("TEST_DB_HOST", "127.0.0.1")
TEST_DB_PORT = os.getenv("TEST_DB_PORT", "55433")
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "esimage_test")
TEST_DB_USER = os.getenv("TEST_DB_USER", "esimage")
TEST_DB_PASSWORD = os.getenv("TEST_DB_PASSWORD", "esimage")

TEST_DATABASE_URL = (
    f"postgresql+psycopg://{TEST_DB_USER}:{TEST_DB_PASSWORD}"
    f"@{TEST_DB_HOST}:{TEST_DB_PORT}/{TEST_DB_NAME}"
)
ADMIN_DATABASE_URL = (
    f"postgresql+psycopg://{TEST_DB_USER}:{TEST_DB_PASSWORD}"
    f"@{TEST_DB_HOST}:{TEST_DB_PORT}/postgres"
)

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("JWT_SECRET", "test-only-secret-esimage-0123456789abcdef")

import pytest  # noqa: E402
from sqlalchemy import create_engine, delete, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def _ensure_database() -> None:
    """测试库不存在时创建。"""
    admin_engine = create_engine(ADMIN_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB_NAME},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
            print(f"[测试] 已创建测试数据库 {TEST_DB_NAME}")
    admin_engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def prepared_database():
    """会话级：准备测试库、重建表并写入种子。"""
    print("[测试] 准备测试数据库……")
    _ensure_database()

    from app import models  # noqa: F401  注册模型
    from app.core.database import Base, SessionLocal, engine
    from app.modules.auth.seed import seed

    print("[测试] 重建测试表结构……")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
    print("[测试] 测试数据库就绪。")
    yield


@pytest.fixture(autouse=True)
def reset_state():
    """每个用例前：清空审计日志，恢复演示账号状态。"""
    from app.core.database import SessionLocal
    from app.models import AuditLog, User

    with SessionLocal() as db:
        db.execute(delete(AuditLog))
        for user in db.scalars(select(User)):
            user.status = "active"
            user.token_version = 0
            user.last_login_at = None
        db.commit()
    yield


@pytest.fixture()
def db_session() -> Session:
    """需要直接改库的用例使用。"""
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        yield db


@pytest.fixture()
def client():
    """FastAPI 测试客户端。"""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)
