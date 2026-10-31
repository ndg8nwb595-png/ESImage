"""用户列表与详情：复用 6 号结构，统计改为真实聚合。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext
from app.core.response import ApiError, ok
from app.models.user import Role, User
from app.modules.admin.accounts.service import build_user_stats, serialize_account
from app.modules.admin.content.service import get_user_or_404
from app.modules.admin.service import (
    USER_STATUSES,
    ensure_content_access,
    local_day_end_exclusive,
    local_day_start,
    page_payload,
    parse_date_range,
    require_permission,
    validate_keyword,
)

router = APIRouter(prefix="/admin/users", tags=["admin-accounts"])

ACCOUNT_PERMISSION = require_permission("admin.accounts.view")
ACCOUNT_ROLES = {"user", "admin", "super_admin"}
ACCOUNT_PAGE_SIZES = {20, 50, 100}


def _validate_page_size(page_size: int) -> int:
    if page_size not in ACCOUNT_PAGE_SIZES:
        raise ApiError(400, 10003, "每页条数不合法")
    return page_size


@router.get("")
def list_users(
    keyword: str | None = Query(None),
    role: str | None = Query(None),
    status: str = Query("all"),
    created_from: str | None = Query(None),
    created_to: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    auth: AuthContext = Depends(ACCOUNT_PERMISSION),
    db: Session = Depends(get_db),
) -> dict:
    """用户列表；筛选与分页遵循 6 号 demo，stats 为真实值。"""
    keyword_value = validate_keyword(keyword)
    role_value = role.strip() if role and role.strip() else None
    if role_value is not None and role_value not in ACCOUNT_ROLES:
        raise ApiError(400, 10003, "角色参数不合法")
    status_value = (status or "all").strip()
    if status_value not in USER_STATUSES | {"all"}:
        raise ApiError(400, 10003, "状态参数不合法")
    size = _validate_page_size(page_size)
    page_number = 1 if page < 1 else page

    start, end = parse_date_range(
        created_from, created_to, message="创建时间范围不合法"
    )

    conditions = []
    if keyword_value is not None:
        pattern = f"%{keyword_value}%"
        conditions.append(
            or_(User.username.ilike(pattern), User.display_name.ilike(pattern))
        )
    if role_value is not None:
        conditions.append(User.roles.any(Role.code == role_value))
    if status_value != "all":
        conditions.append(User.status == status_value)
    if start is not None:
        conditions.append(User.created_at >= local_day_start(start))
    if end is not None:
        conditions.append(User.created_at < local_day_end_exclusive(end))

    total = int(
        db.scalar(select(func.count()).select_from(User).where(*conditions)) or 0
    )
    users = list(
        db.scalars(
            select(User)
            .where(*conditions)
            .order_by(User.created_at.desc(), User.id.desc())
            .offset((page_number - 1) * size)
            .limit(size)
        )
    )
    stats = build_user_stats(db, [user.id for user in users])
    items = [serialize_account(user, stats[user.id]) for user in users]
    print(f"[用户统计] 用户列表 role={role_value} status={status_value} 共 {total} 条")
    return ok(page_payload(items, total, page_number, size))


@router.get("/{user_id}")
def get_user_detail(
    user_id: int,
    auth: AuthContext = Depends(ACCOUNT_PERMISSION),
    db: Session = Depends(get_db),
) -> dict:
    """用户详情；管理员不能查看超管账号。"""
    user = get_user_or_404(db, user_id)
    ensure_content_access(db, auth, user.id)
    stats = build_user_stats(db, [user.id])[user.id]
    print(f"[用户统计] 用户详情 user={user.id} stats={stats}")
    return ok(serialize_account(user, stats))
