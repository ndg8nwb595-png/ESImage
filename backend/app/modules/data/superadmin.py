"""首个超管初始化（10 号 §10.2 / 接口文档 §4.4）。

用户名与密码必须显式来自环境变量，禁止代码内默认密码；缺失、弱口令时失败。
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import Role, User

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,20}$")
WEAK_PASSWORDS = {"admin", "password", "12345678", "qwerty123"}


class SuperAdminError(Exception):
    """超管初始化失败（中文原因）。"""


def validate_super_admin(username: str, password: str) -> None:
    """校验超管用户名与密码；不合法时抛 :class:`SuperAdminError`。"""
    if not username or not username.strip():
        raise SuperAdminError("缺少环境变量 INITIAL_SUPER_ADMIN_USERNAME")
    if not password:
        raise SuperAdminError("缺少环境变量 INITIAL_SUPER_ADMIN_PASSWORD")

    username = username.strip()
    if not USERNAME_RE.match(username):
        raise SuperAdminError("超管用户名需为 4~20 位字母、数字或下划线")

    if len(password) < 8:
        raise SuperAdminError("超管密码至少 8 位")
    has_alpha = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    if not (has_alpha and has_digit):
        raise SuperAdminError("超管密码必须同时包含字母与数字")
    if password.lower() in WEAK_PASSWORDS:
        raise SuperAdminError("超管密码过于简单，请更换")


def init_super_admin(db: Session, username: str, password: str) -> tuple[bool, User]:
    """创建或复用首个超管。

    返回 ``(created, user)``：账号已存在时不重置密码、不重复授予角色。
    """
    username = username.strip()
    validate_super_admin(username, password)

    user = db.scalar(select(User).where(User.username == username))
    created = user is None
    if created:
        user = User(
            username=username,
            display_name=username,
            password_hash=hash_password(password),
            status="active",
            token_version=0,
        )
        db.add(user)
        db.flush()

    role = db.scalar(select(Role).where(Role.code == "super_admin"))
    if role is None:
        raise SuperAdminError("缺少 super_admin 角色，请先执行 seed")
    if role not in user.roles:
        user.roles.append(role)

    db.commit()
    return created, user
