"""跨模块共享的校验、权限、时间与 URL 工具。

workspace 与 generation 共用这些函数，避免各模块重复实现导致错误码漂移。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import AuthContext, get_current_auth
from app.core.response import ApiError
from app.models.workspace import CreativeSession


def require_permission(code: str) -> Callable[..., AuthContext]:
    """生成权限校验依赖；缺少权限返回 403/20005。"""

    def dependency(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
        if code not in auth.permissions:
            raise ApiError(403, 20005, "无权限")
        return auth

    return dependency


def require_any_permission(*codes: str) -> Callable[..., AuthContext]:
    """任意一个权限满足即可；用于历史/生成共用的媒体读取接口。"""

    def dependency(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
        if not any(code in auth.permissions for code in codes):
            raise ApiError(403, 20005, "无权限")
        return auth

    return dependency


def validate_product_name(value: str | None) -> str:
    """商品名称：去首尾空格后 1~60 字符。"""
    if value is None or value.strip() == "":
        raise ApiError(400, 10002, "请先填写商品名称")
    name = value.strip()
    if len(name) > 60:
        raise ApiError(400, 10004, "商品名称不能超过 60 个字符")
    return name


def validate_style_text(value: str | None) -> str | None:
    """风格：纯空格视为未填写；填写时 1~50 字符。"""
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    if len(text) > 50:
        raise ApiError(400, 10004, "风格不能超过 50 个字符")
    return text


def validate_idempotency_key(value: str | None, field_name: str) -> str:
    """幂等键：UUID，非空且不超过 64 字符。"""
    if value is None or value.strip() == "":
        raise ApiError(400, 10002, f"缺少{field_name}")
    key = value.strip()
    if len(key) > 64:
        raise ApiError(400, 10004, f"{field_name}不能超过 64 个字符")
    try:
        uuid.UUID(key)
    except (ValueError, AttributeError) as exc:
        raise ApiError(400, 10003, f"{field_name} 需为 UUID") from exc
    return key


def get_owned_session(
    db: Session, user_id: int, session_id: int, *, allow_hidden: bool = False
) -> CreativeSession:
    """读取当前用户的会话；不存在、已隐藏或不属于当前用户统一 30013。"""
    session = db.get(CreativeSession, session_id)
    if session is None or session.user_id != user_id:
        raise ApiError(404, 30013, "会话不存在")
    if session.status != "active" and not allow_hidden:
        raise ApiError(404, 30013, "会话不存在")
    return session


def session_title_from_product(product_name: str) -> str:
    """首次生成建会话：取商品名称，最多 50 字符。"""
    title = product_name.strip()[:50]
    return title or "未命名会话"


def to_iso(value: datetime | None) -> str | None:
    """统一输出东八区 ISO 8601；数据库返回 UTC 时自动转换。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(settings.TZ).isoformat()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def image_content_url(image_id: int) -> str:
    return f"/api/v1/images/{image_id}/content"


def image_thumbnail_url(image_id: int) -> str:
    return f"/api/v1/images/{image_id}/thumbnail"


def filename_timestamp(value: datetime | None) -> str:
    """文件名时间戳：东八区 yyyyMMddHHmmss。"""
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(settings.TZ).strftime("%Y%m%d%H%M%S")


def safe_filename_part(value: str) -> str:
    """把文件名非法字符替换为下划线。"""
    invalid = set('\\/:*?"<>|\r\n\t')
    cleaned = "".join("_" if ch in invalid else ch for ch in value).strip()
    return cleaned or "未命名商品"
