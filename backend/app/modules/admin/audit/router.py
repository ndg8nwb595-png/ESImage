"""操作日志：列表与详情（6 号 PRD 最小 demo，仅超管）。

接口文档使用 `operator` / `start_time` / `end_time`；已合并的前端使用
`keyword` / `created_from` / `created_to`。为不破坏下游，两套参数都接受，
响应同时返回 `log_id` 与旧的 `id` 等字段（双兼容）。
"""

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
    """同时返回 6 号文档字段与前端已使用的旧字段，避免破坏下游。"""
    return {
        "id": log.id,
        "log_id": log.id,
        "user_id": log.user_id,
        "operator_user_id": log.user_id,
        "username_snapshot": log.username_snapshot,
        "operator_username": log.username_snapshot,
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
        raise ApiError(400, 10003, "时间范围不合法") from None
    return datetime.combine(day, time.min, tzinfo=settings.TZ).astimezone(timezone.utc)


def _parse_time(value: str | None) -> datetime | None:
    """解析 ISO 8601 带时区时间；无时区按东八区处理。"""
    if not value or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, 10003, "时间范围不合法") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=settings.TZ)
    return parsed.astimezone(timezone.utc)


@router.get("/audit-logs")
def list_audit_logs(
    keyword: str | None = None,
    operator: str | None = None,
    action: str | None = None,
    result: str = "all",
    created_from: str | None = None,
    created_to: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    page: int = Query(1),
    page_size: int = Query(20),
    auth: AuthContext = Depends(require_permission("admin.audit.view")),
    db: Session = Depends(get_db),
) -> dict:
    """操作日志列表。"""
    if result not in ("success", "failed", "all", None):
        raise ApiError(400, 10003, "结果参数不合法")

    operator_text = (operator or "").strip()
    if len(operator_text) > 20:
        raise ApiError(400, 10004, "操作人关键词不能超过 20 个字符")

    if page_size < 1 or page_size > 100:
        raise ApiError(400, 10003, "每页条数不合法")
    # 接口文档 §1.5：page 小于 1 按 1 处理
    page = max(1, page)

    # 兼容两套时间参数：日期范围与 ISO 时间范围
    from_utc = _parse_day(created_from)
    to_utc = _parse_day(created_to)
    if from_utc and to_utc and from_utc > to_utc:
        raise ApiError(400, 10003, "时间范围不合法")
    start_utc = _parse_time(start_time)
    end_utc = _parse_time(end_time)
    if start_utc and end_utc and start_utc > end_utc:
        raise ApiError(400, 10003, "时间范围不合法")

    filters = []
    if operator_text:
        filters.append(AuditLog.username_snapshot.ilike(f"%{operator_text}%"))
    if keyword and keyword.strip():
        kw = f"%{keyword.strip()}%"
        filters.append(or_(AuditLog.username_snapshot.ilike(kw), AuditLog.action.ilike(kw)))
    if action and action.strip():
        filters.append(AuditLog.action == action.strip())
    if result in ("success", "failed"):
        filters.append(AuditLog.result == result)
    if from_utc:
        filters.append(AuditLog.created_at >= from_utc)
    if to_utc:
        filters.append(AuditLog.created_at < to_utc + timedelta(days=1))
    if start_utc:
        filters.append(AuditLog.created_at >= start_utc)
    if end_utc:
        filters.append(AuditLog.created_at <= end_utc)

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
        raise ApiError(404, 30019, "操作日志不存在")
    return ok(_audit_payload(log))
