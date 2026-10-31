"""登录、当前用户、退出登录三个接口。"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.database import get_db
from app.core.deps import AuthContext, get_current_auth
from app.core.response import ApiError, ok
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.modules.auth.schemas import LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])

# 用户名：去除首尾空格后 4~20 位字母、数字、下划线；区分大小写
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,20}$")

# 用户不存在时也执行一次 bcrypt 校验，降低通过响应时间判断账号是否存在的可能
_DUMMY_PASSWORD_HASH = hash_password("__esimage_timing_dummy__")


def _user_roles_and_permissions(user: User) -> tuple[list[str], list[str]]:
    roles = sorted(role.code for role in user.roles)
    permissions = sorted({permission.code for role in user.roles for permission in role.permissions})
    return roles, permissions


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict:
    """账号密码登录。"""
    # 1. 用户名去首尾空格 + 格式校验
    raw_username = payload.username
    if raw_username is None or raw_username.strip() == "":
        raise ApiError(400, 10002, "请输入用户名")
    username = raw_username.strip()
    if not USERNAME_RE.fullmatch(username):
        raise ApiError(400, 10003, "用户名需为 4~20 位字母、数字或下划线")

    # 2. 密码不做 trim；长度 8~32
    password = payload.password
    if password is None or password == "":
        raise ApiError(400, 10002, "请输入密码")
    if not (8 <= len(password) <= 32):
        raise ApiError(400, 10003, "密码长度需为 8~32 位")

    remember_me = bool(payload.remember_me)

    # 3. 精确查询用户（包含已删除账号）
    user = db.scalar(select(User).where(User.username == username))

    # 4. 统一校验密码；用户不存在时对固定哈希校验以对齐耗时
    password_ok = verify_password(
        password, user.password_hash if user else _DUMMY_PASSWORD_HASH
    )
    if user is None or not password_ok or user.status != "active":
        # 登录失败审计：只记录用户名快照，不含密码
        write_audit(
            db,
            request,
            user_id=user.id if user else None,
            username_snapshot=username,
            action="auth.login",
            result="failed",
            detail={"reason": "bad_credentials"},
        )
        db.commit()
        raise ApiError(401, 20001, "用户名或密码错误")

    # 5. 签发 token、更新最后登录时间、写成功审计
    role_codes, permission_codes = _user_roles_and_permissions(user)
    token, expires_at, _ = create_access_token(user, role_codes, permission_codes, remember_me)

    user.last_login_at = datetime.now(timezone.utc)
    write_audit(
        db,
        request,
        user_id=user.id,
        username_snapshot=user.username,
        action="auth.login",
        result="success",
        detail=None,
    )
    db.commit()

    return ok(
        {
            "token": token,
            "expires_at": expires_at,
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "avatar_url": None,
                "roles": role_codes,
                "permissions": permission_codes,
            },
        }
    )


@router.get("/me")
def me(auth: AuthContext = Depends(get_current_auth)) -> dict:
    """获取当前用户、角色与权限。"""
    return ok(
        {
            "user": {
                "id": auth.user.id,
                "username": auth.user.username,
                "display_name": auth.user.display_name,
                "avatar_url": None,
            },
            "roles": auth.roles,
            "permissions": auth.permissions,
        }
    )


@router.post("/logout")
def logout(
    request: Request,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """退出登录：只写审计，不维护服务端黑名单。"""
    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action="auth.logout",
        result="success",
        detail=None,
    )
    db.commit()
    return ok(None)
