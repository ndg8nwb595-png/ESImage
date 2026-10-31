"""账号与权限：用户 CRUD、禁用/启用/软删除/恢复、角色与权限点（6 号 PRD 最小 demo）。"""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.audit import write_audit
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.core.security import hash_password
from app.models.user import Permission, Role, User, user_roles
from app.modules.admin.accounts.schemas import (
    CreateUserRequest,
    ResetPasswordRequest,
    RolePermissionsRequest,
    UpdateUserRequest,
)
from app.modules.admin.accounts.service import build_user_stats
from app.modules.workspace.service import to_iso

router = APIRouter(tags=["admin-accounts"])

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,20}$")

# 允许的角色组合（1~2 个角色）
VALID_ROLE_COMBOS = {
    ("user",),
    ("admin",),
    ("super_admin",),
    ("admin", "user"),
    ("super_admin", "user"),
}


def _roles_of(user: User) -> set[str]:
    return {role.code for role in user.roles}


def _is_super(user: User) -> bool:
    return "super_admin" in _roles_of(user)


def _role_objects(db: Session, codes: list[str]) -> list[Role]:
    return list(db.scalars(select(Role).where(Role.code.in_(codes))))


def _get_target_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, 30017, "用户不存在")
    return user


def _validate_role_combo(roles: list[str]) -> tuple[str, ...]:
    combo = tuple(sorted(roles))
    if combo not in VALID_ROLE_COMBOS:
        raise ApiError(409, 30009, "角色组合不合法")
    return combo


def _count_active_super(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .join(user_roles, User.id == user_roles.c.user_id)
            .join(Role, Role.id == user_roles.c.role_id)
            .where(User.status == "active", Role.code == "super_admin")
        )
        or 0
    )


def _user_stats(db: Session, user_id: int) -> dict:
    """单用户统计：与列表共用批量聚合口径。"""
    return build_user_stats(db, [user_id])[user_id]


def _user_payload(db: Session, user: User, stats: dict | None = None) -> dict:
    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "roles": [{"code": r.code, "name": r.name} for r in user.roles],
        "status": user.status,
        "stats": stats if stats is not None else _user_stats(db, user.id),
        "last_login_at": to_iso(user.last_login_at),
        "created_at": to_iso(user.created_at),
        "updated_at": to_iso(user.updated_at),
        "deleted_at": to_iso(user.deleted_at),
    }


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ApiError(400, 10003, "创建时间范围不合法") from None
    return datetime.combine(day, time.min, tzinfo=settings.TZ).astimezone(timezone.utc)


def _forbid_admin_on_super(auth: AuthContext, target: User) -> None:
    """管理员不能操作超管账号。"""
    if not _is_super(auth.user) and _is_super(target):
        raise ApiError(403, 20006, "无权操作超管账号")


@router.get("/users")
def list_users(
    keyword: str | None = None,
    role: str | None = None,
    status: str = "all",
    created_from: str | None = None,
    created_to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20),
    auth: AuthContext = Depends(require_permission("admin.accounts.view")),
    db: Session = Depends(get_db),
) -> dict:
    """用户列表。"""
    kw = (keyword or "").strip()
    if len(kw) > 50:
        raise ApiError(400, 10004, "关键词不能超过 50 个字符")
    if role is not None and role not in ("user", "admin", "super_admin"):
        raise ApiError(400, 10003, "角色参数不合法")
    if status not in ("active", "disabled", "deleted", "all"):
        raise ApiError(400, 10003, "状态参数不合法")
    if page_size not in (20, 50, 100):
        raise ApiError(400, 10003, "每页条数不合法")

    from_utc = _parse_date(created_from)
    to_utc = _parse_date(created_to)
    if from_utc and to_utc and from_utc > to_utc:
        raise ApiError(400, 10003, "创建时间范围不合法")

    filters = []
    if kw:
        filters.append(or_(User.username.ilike(f"%{kw}%"), User.display_name.ilike(f"%{kw}%")))
    if status == "deleted":
        filters.append(User.status == "deleted")
    elif status in ("active", "disabled"):
        filters.append(User.status == status)
    if from_utc:
        filters.append(User.created_at >= from_utc)
    if to_utc:
        filters.append(User.created_at < to_utc + timedelta(days=1))
    if role:
        filters.append(User.roles.any(Role.code == role))

    base = select(User).where(*filters)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    users = list(
        db.scalars(
            base.order_by(User.created_at.desc(), User.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    stats_map = build_user_stats(db, [u.id for u in users])
    return ok(
        {
            "items": [_user_payload(db, u, stats_map[u.id]) for u in users],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@router.post("/users")
def create_user(
    payload: CreateUserRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.accounts.create")),
    db: Session = Depends(get_db),
) -> dict:
    """新建账号。"""
    username = (payload.username or "").strip()
    display_name = (payload.display_name or "").strip()
    password = payload.password or ""
    status = payload.status or "active"

    if not username or not display_name or not password or payload.roles is None:
        raise ApiError(400, 10002, "请填写完整账号信息")
    if not USERNAME_RE.fullmatch(username):
        raise ApiError(400, 10003, "用户名需为 4~20 位字母、数字或下划线")
    if len(display_name) > 30:
        raise ApiError(400, 10004, "显示名不能超过 30 个字符")
    if not (8 <= len(password) <= 32):
        raise ApiError(400, 10004, "密码长度需为 8~32 位")
    if status not in ("active", "disabled"):
        raise ApiError(400, 10003, "状态参数不合法")

    combo = _validate_role_combo(payload.roles)
    if "super_admin" in combo and not _is_super(auth.user):
        raise ApiError(403, 20005, "无权分配超管角色")

    if db.scalar(select(User).where(User.username == username)) is not None:
        raise ApiError(409, 30010, "用户名已存在")

    user = User(
        username=username,
        display_name=display_name,
        password_hash=hash_password(password),
        status=status,
    )
    user.roles = _role_objects(db, list(combo))
    db.add(user)
    write_audit(
        db, request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action="account.create",
        result="success",
        detail={"target_username": username},
    )
    db.commit()
    db.refresh(user)
    return ok(_user_payload(db, user))


@router.get("/users/{user_id}")
def get_user(
    user_id: int,
    auth: AuthContext = Depends(require_permission("admin.accounts.view")),
    db: Session = Depends(get_db),
) -> dict:
    """用户详情。"""
    target = _get_target_user(db, user_id)
    if not _is_super(auth.user) and _is_super(target):
        raise ApiError(403, 20006, "无权操作超管账号")
    return ok(_user_payload(db, target))


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.accounts.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """编辑显示名、角色、状态。"""
    target = _get_target_user(db, user_id)
    actor_is_super = _is_super(auth.user)
    is_self = auth.user.id == target.id

    changes = {}
    if payload.display_name is not None:
        changes["display_name"] = payload.display_name
    if payload.roles is not None:
        changes["roles"] = payload.roles
    if payload.status is not None:
        changes["status"] = payload.status
    if not changes:
        raise ApiError(400, 10002, "请至少修改一个字段")

    if not actor_is_super and _is_super(target):
        raise ApiError(403, 20006, "无权操作超管账号")
    if is_self and not actor_is_super and ("roles" in changes or "status" in changes):
        raise ApiError(403, 20007, "不能修改自己的角色或状态")
    if is_self and actor_is_super:
        if "status" in changes:
            raise ApiError(403, 20007, "不能修改自己的状态")
        if "roles" in changes and "super_admin" not in changes["roles"]:
            raise ApiError(403, 20007, "不能移除自己的超管角色")
    if not actor_is_super and not is_self and "admin" in _roles_of(target) and "roles" in changes:
        raise ApiError(403, 20005, "无权修改其他管理员的角色")
    if not actor_is_super and "roles" in changes and "super_admin" in changes["roles"]:
        raise ApiError(403, 20005, "无权分配超管角色")

    new_status = target.status
    new_roles = _roles_of(target)
    if "display_name" in changes:
        dn = changes["display_name"].strip()
        if not dn or len(dn) > 30:
            raise ApiError(400, 10004, "显示名不能超过 30 个字符")
        target.display_name = dn
    if "roles" in changes:
        combo = _validate_role_combo(changes["roles"])
        new_roles = set(combo)
    if "status" in changes:
        if changes["status"] not in ("active", "disabled"):
            raise ApiError(400, 10003, "状态参数不合法")
        new_status = changes["status"]

    # 最后可用超管保护
    if _is_super(target) and target.status == "active":
        losing_super = ("roles" in changes and "super_admin" not in new_roles) or (
            "status" in changes and new_status != "active"
        )
        if losing_super and _count_active_super(db) <= 1:
            raise ApiError(409, 30011, "必须保留至少一个可用超管")

    if "roles" in changes:
        target.roles = _role_objects(db, list(new_roles))
    if "status" in changes:
        target.status = new_status

    write_audit(
        db, request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action="account.update",
        result="success",
        detail={"target_username": target.username},
    )
    db.commit()
    return ok(_user_payload(db, target))


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: ResetPasswordRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.accounts.reset_password")),
    db: Session = Depends(get_db),
) -> dict:
    """重置密码，token_version 递增使旧 token 失效。"""
    target = _get_target_user(db, user_id)
    new_password = (payload.new_password or "").strip()
    if not new_password:
        raise ApiError(400, 10002, "请输入新密码")
    if not (8 <= len(new_password) <= 32):
        raise ApiError(400, 10004, "密码长度需为 8~32 位")

    _forbid_admin_on_super(auth, target)
    if _is_super(auth.user) and auth.user.id == target.id:
        raise ApiError(403, 20007, "请通过个人中心修改自己的密码")

    target.password_hash = hash_password(new_password)
    target.token_version += 1
    write_audit(
        db, request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action="account.reset_password",
        result="success",
        detail={"target_username": target.username},
    )
    db.commit()
    return ok(None)


@router.post("/users/{user_id}/disable")
def disable_user(
    user_id: int,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.accounts.disable")),
    db: Session = Depends(get_db),
) -> dict:
    """禁用账号。"""
    target = _get_target_user(db, user_id)
    _forbid_admin_on_super(auth, target)
    if auth.user.id == target.id:
        raise ApiError(403, 20007, "不能对自己执行该操作")
    if target.status == "deleted":
        raise ApiError(409, 30018, "当前账号状态不允许该操作")
    if target.status == "disabled":
        return ok(_user_payload(db, target))
    if _is_super(target) and _count_active_super(db) <= 1:
        raise ApiError(409, 30011, "必须保留至少一个可用超管")

    target.status = "disabled"
    target.token_version += 1
    write_audit(db, request, user_id=auth.user.id, username_snapshot=auth.user.username, action="account.disable", result="success", detail={"target_username": target.username})
    db.commit()
    return ok(_user_payload(db, target))


@router.post("/users/{user_id}/enable")
def enable_user(
    user_id: int,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.accounts.disable")),
    db: Session = Depends(get_db),
) -> dict:
    """启用账号。"""
    target = _get_target_user(db, user_id)
    _forbid_admin_on_super(auth, target)
    if target.status == "deleted":
        raise ApiError(409, 30018, "当前账号状态不允许该操作")
    if target.status == "active":
        return ok(_user_payload(db, target))

    target.status = "active"
    write_audit(db, request, user_id=auth.user.id, username_snapshot=auth.user.username, action="account.enable", result="success", detail={"target_username": target.username})
    db.commit()
    return ok(_user_payload(db, target))


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.accounts.delete")),
    db: Session = Depends(get_db),
) -> dict:
    """软删除账号。"""
    target = _get_target_user(db, user_id)
    _forbid_admin_on_super(auth, target)
    if auth.user.id == target.id:
        raise ApiError(403, 20007, "不能对自己执行该操作")
    if target.status == "deleted":
        raise ApiError(409, 30018, "当前账号状态不允许该操作")
    if _is_super(target) and target.status == "active" and _count_active_super(db) <= 1:
        raise ApiError(409, 30011, "必须保留至少一个可用超管")

    target.status = "deleted"
    target.deleted_at = datetime.now(timezone.utc)
    target.token_version += 1
    write_audit(db, request, user_id=auth.user.id, username_snapshot=auth.user.username, action="account.delete", result="success", detail={"target_username": target.username})
    db.commit()
    return ok(None)


@router.post("/users/{user_id}/restore")
def restore_user(
    user_id: int,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.accounts.delete")),
    db: Session = Depends(get_db),
) -> dict:
    """恢复软删除账号。"""
    target = _get_target_user(db, user_id)
    _forbid_admin_on_super(auth, target)
    if target.status != "deleted":
        raise ApiError(409, 30018, "当前账号状态不允许该操作")

    target.status = "active"
    target.deleted_at = None
    target.token_version += 1
    write_audit(db, request, user_id=auth.user.id, username_snapshot=auth.user.username, action="account.restore", result="success", detail={"target_username": target.username})
    db.commit()
    return ok(_user_payload(db, target))


@router.get("/roles")
def list_roles(
    auth: AuthContext = Depends(require_permission("admin.roles.view")),
    db: Session = Depends(get_db),
) -> dict:
    """三个角色与权限点目录。"""
    roles = list(db.scalars(select(Role).order_by(Role.id)))
    permissions = list(db.scalars(select(Permission).order_by(Permission.group_name, Permission.code)))
    all_codes = [p.code for p in permissions]
    return ok(
        {
            "roles": [
                {
                    "code": r.code,
                    "name": r.name,
                    "editable": r.code != "super_admin",
                    "permissions": all_codes if r.code == "super_admin" else [p.code for p in r.permissions],
                }
                for r in roles
            ],
            "permissions": [
                {
                    "code": p.code,
                    "name": p.name,
                    "type": p.type,
                    "group_name": p.group_name,
                    "is_super_only": p.is_super_only,
                }
                for p in permissions
            ],
        }
    )


@router.put("/roles/{code}/permissions")
def update_role_permissions(
    code: str,
    payload: RolePermissionsRequest,
    request: Request,
    auth: AuthContext = Depends(require_permission("admin.roles.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """保存角色权限点（仅超管）。"""
    if code not in ("user", "admin"):
        raise ApiError(403, 20005, "无权限")

    known = {p.code for p in db.scalars(select(Permission))}
    if any(c not in known for c in payload.permissions):
        raise ApiError(400, 10003, "权限点参数不合法")
    super_only = {p.code for p in db.scalars(select(Permission).where(Permission.is_super_only.is_(True)))}
    if any(c in super_only for c in payload.permissions):
        raise ApiError(409, 30015, "超管专属权限不能授予该角色")

    role = db.scalar(select(Role).where(Role.code == code))
    role.permissions = list(db.scalars(select(Permission).where(Permission.code.in_(payload.permissions))))
    write_audit(db, request, user_id=auth.user.id, username_snapshot=auth.user.username, action="role.permissions.update", result="success", detail={"role_code": code})
    db.commit()
    return ok(None)
