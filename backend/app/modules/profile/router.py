"""个人中心：查看/修改资料（9 号 PRD §5.7）。"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.user import User
from app.modules.profile.schemas import ProfileUpdateRequest

router = APIRouter(tags=["profile"])

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _profile_payload(user: User) -> dict:
    return {
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "avatar_url": None,
    }


@router.get("/profile")
def get_profile(auth: AuthContext = Depends(require_permission("user.profile"))) -> dict:
    """当前用户资料。"""
    return ok(_profile_payload(auth.user))


@router.patch("/profile")
def update_profile(
    payload: ProfileUpdateRequest,
    auth: AuthContext = Depends(require_permission("user.profile")),
    db: Session = Depends(get_db),
) -> dict:
    """修改显示名、邮箱；用户名不可修改。"""
    display_name = (payload.display_name or "").strip()
    if not display_name:
        raise ApiError(400, 10002, "显示名不能为空")
    if len(display_name) > 30:
        raise ApiError(400, 10004, "显示名不能超过 30 个字符")

    email = (payload.email or "").strip() or None
    if email is not None:
        if len(email) > 255:
            raise ApiError(400, 10004, "邮箱不能超过 255 个字符")
        if not EMAIL_RE.match(email):
            raise ApiError(400, 10003, "邮箱格式错误")

    auth.user.display_name = display_name
    auth.user.email = email
    db.commit()
    return ok(_profile_payload(auth.user))
