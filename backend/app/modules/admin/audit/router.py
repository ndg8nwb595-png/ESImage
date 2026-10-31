"""操作日志：列表与详情（6 号 PRD 最小 demo，仅超管）。"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.audit import AuditLog
from app.modules.workspace.service import to_iso

router = APIRouter(tags=["admin-audit"])


def _audit_payload(log: AuditLog) -> dict:
    return {
        "id": log.id,
        "user_id": log.user_id,
        "username_snapshot": log.username_snapshot,
        "action": log.action,
        "target_type": log.target_type,
        "target_id": log.target_id,
        "result": log.result,
        "ip": log.ip,
        "user_agent": log.user_agent,
        "detail": log.detail,
        "created_at": to_iso(log.created_at),
    }


def _parse_day(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ApiError(400, 10003, "日期格式不合法") from None
    return datetime.combine(day, time.min, tzinfo=settings.TZ).astimezone(timezone.utc)


@router.get("/audit-logs")
def list_audit_logs(
    keyword: str | None = None,
    action: str | None = None,
    result: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("admin.audit.view")),
    db: Session = Depends(get_db),
) -> dict:
    """操作日志列表。"""
    if result is not None and result not in ("success", "failed"):
        raise ApiError(400, 10003, "结果参数不合法")

    from_utc = _parse_day(created_from)
    to_utc = _parse_day(created_to)
    if from_utc and to_utc and from_utc > to_utc:
        raise ApiError(400, 10003, "日期范围不合法")

    filters = []
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        filters.append(or_(AuditLog.username_snapshot.ilike(kw), AuditLog.action.ilike(kw)))
    if action and action.strip():
        filters.append(AuditLog.action == action.strip())
    if result:
        filters.append(AuditLog.result == result)
    if from_utc:
        filters.append(AuditLog.created_at >= from_utc)
    if to_utc:
        filters.append(AuditLog.created_at < to_utc + timedelta(days=1))

    base = select(AuditLog).where(*filters)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    logs = list(
        db.scalars(
            base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return ok(
        {
            "items": [_audit_payload(log) for log in logs],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/audit-logs/{log_id}")
def get_audit_log(
    log_id: int,
    auth: AuthContext = Depends(require_permission("admin.audit.view")),
    db: Session = Depends(get_db),
) -> dict:
    """操作日志详情。"""
    log = db.get(AuditLog, log_id)
    if log is None:
        raise ApiError(404, 30017, "日志不存在")
    return ok(_audit_payload(log))
