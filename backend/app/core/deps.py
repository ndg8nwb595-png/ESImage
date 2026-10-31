"""鉴权依赖：解析 Bearer token、校验账号状态与权限点。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.response import ApiError
from app.core.security import decode_access_token
from app.models.user import Permission, User


@dataclass
class AuthContext:
    """当前请求的登录上下文。"""

    user: User
    roles: list[str]
    permissions: list[str]


def _role_codes(user: User) -> list[str]:
    return sorted(role.code for role in user.roles)


def _permission_codes(db: Session, user: User) -> list[str]:
    """读取当前用户权限码。

    6 号文档 §1.4：拥有 super_admin 角色时直接拥有全部权限码，不读取
    role_permissions；其他角色取所分配角色在 role_permissions 中的并集。
    """
    if any(role.code == "super_admin" for role in user.roles):
        return sorted(db.scalars(select(Permission.code)).all())
    codes = {permission.code for role in user.roles for permission in role.permissions}
    return sorted(codes)


def get_current_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    """按 6 号接口文档 §1.4 的顺序校验 token。

    1. 格式/签名 -> 20003
    2. exp -> 20002
    3. 用户存在 -> 20003
    4. status=active -> 20004（账号状态先于 token_version，保证禁用/删除统一返回 20004）
    5. token_version 一致 -> 20003
    6. 读取角色与权限
    """
    authorization = request.headers.get("authorization")

    # 1. 缺失或格式错误
    if not authorization:
        raise ApiError(401, 20003, "token 无效")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise ApiError(401, 20003, "token 无效")
    token = parts[1].strip()

    # 2. 签名与过期时间
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, 20002, "登录已过期") from exc
    except jwt.InvalidTokenError as exc:
        raise ApiError(401, 20003, "token 无效") from exc

    # 3. 用户是否存在
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError) as exc:
        raise ApiError(401, 20003, "token 无效") from exc
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(401, 20003, "token 无效")

    # 4. 账号状态（先于 token_version）
    if user.status != "active":
        raise ApiError(403, 20004, "账号不可用")

    # 5. token_version 是否一致
    try:
        token_version = int(payload.get("token_version", -1))
    except (TypeError, ValueError) as exc:
        raise ApiError(401, 20003, "token 无效") from exc
    if token_version != user.token_version:
        raise ApiError(401, 20003, "token 无效")

    return AuthContext(
        user=user,
        roles=_role_codes(user),
        permissions=_permission_codes(db, user),
    )


def require_permission(code: str) -> Callable[..., AuthContext]:
    """要求当前用户拥有指定权限点；缺少返回 403/20005。"""

    def dependency(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
        if code not in auth.permissions:
            raise ApiError(403, 20005, "无权限")
        return auth

    return dependency


def require_any_permission(*codes: str) -> Callable[..., AuthContext]:
    """要求拥有任一权限点；历史页预览/缩略图需 user.history 或 user.generate。"""

    def dependency(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
        if not any(code in auth.permissions for code in codes):
            raise ApiError(403, 20005, "无权限")
        return auth

    return dependency
