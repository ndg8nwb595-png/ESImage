"""初始超管种子与强密码校验。

- 用户名满足 `^[A-Za-z0-9_]{4,20}$`。
- 密码长度 ≥12 且至少含大写、小写、数字、符号中的 3 类，且不得与用户名相同。
- 已存在时跳过，不重置密码、不改变角色与状态。
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.user import Role, User

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,20}$")


class InitialAdminConfigError(ValueError):
    """初始超管配置不合法（缺失或强度不足）。"""


def _password_categories(password: str) -> int:
    return sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )


def validate_initial_admin() -> tuple[str, str]:
    """校验并返回 (username, password)；不合法时抛出 InitialAdminConfigError。"""
    username = settings.ADMIN_INITIAL_USERNAME.strip()
    password = settings.ADMIN_INITIAL_PASSWORD

    if not _USERNAME_RE.match(username):
        raise InitialAdminConfigError(
            "初始超管用户名不合法：需满足 ^[A-Za-z0-9_]{4,20}$（由 ADMIN_INITIAL_USERNAME 提供）"
        )
    if not password:
        raise InitialAdminConfigError(
            "缺少 ADMIN_INITIAL_PASSWORD：首次初始化必须设置初始超管密码"
        )
    if len(password) < 12:
        raise InitialAdminConfigError("初始超管密码过弱：长度需 ≥12 位")
    if _password_categories(password) < 3:
        raise InitialAdminConfigError("初始超管密码过弱：需包含大写、小写、数字、符号中的至少 3 类")
    if password == username:
        raise InitialAdminConfigError("初始超管密码不得与用户名相同")
    return username, password


def seed_initial_admin(db: Session) -> None:
    """创建唯一初始超管（幂等）。调用前应先执行角色种子。"""
    username, password = validate_initial_admin()

    role = db.scalar(select(Role).where(Role.code == "super_admin"))
    if role is None:
        raise InitialAdminConfigError("缺少 super_admin 角色：请先执行角色种子")

    existing = db.scalar(select(User).where(User.username == username))
    if existing is not None:
        print(f"[种子] 初始超管 {username} 已存在，跳过")
        return

    user = User(
        username=username,
        display_name="超管",
        password_hash=hash_password(password),
        status="active",
        token_version=0,
    )
    user.roles.append(role)
    db.add(user)
    db.flush()
    print(f"[种子] 新建初始超管 {username}")
