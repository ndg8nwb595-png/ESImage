"""审计日志写入。"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def _client_ip(request: Request) -> str | None:
    """优先取反向代理透传的 X-Forwarded-For 首个地址。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    if request.client:
        return request.client.host[:45]
    return None


def write_audit(
    db: Session,
    request: Request,
    *,
    user_id: int | None,
    username_snapshot: str | None,
    action: str,
    result: str,
    detail: dict[str, Any] | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
) -> None:
    """写一条审计日志；不包含密码、JWT 等敏感信息。

    target_type / target_id 为 6 号文档 §2.5 要求的对象类型与对象标识，
    例如 account / zhangsan、role / admin。
    """
    db.add(
        AuditLog(
            user_id=user_id,
            username_snapshot=username_snapshot,
            action=action,
            target_type=target_type,
            target_id=target_id,
            result=result,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            detail=detail,
        )
    )
