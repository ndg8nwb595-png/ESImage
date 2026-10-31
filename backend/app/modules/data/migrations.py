"""Alembic 迁移命令封装。"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext

from app.modules.data.config import config
from app.modules.data.db import engine

_BACKEND_DIR = Path(__file__).resolve().parents[3]


def _alembic_config() -> Config:
    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", config.DATABASE_URL)
    return cfg


def upgrade(revision: str = "head") -> None:
    command.upgrade(_alembic_config(), revision)


def downgrade(revision: str) -> None:
    command.downgrade(_alembic_config(), revision)


def current_revision() -> str | None:
    with engine.connect() as conn:
        context = MigrationContext.configure(conn)
        return context.get_current_revision()
