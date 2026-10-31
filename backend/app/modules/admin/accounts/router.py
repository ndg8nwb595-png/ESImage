"""账号与权限：用户 CRUD、禁用/启用/软删除/恢复、角色与权限点（6 号 PRD 最小 demo）。

接口与错误码对齐 `docs/prd/6-管理后台-账号与权限/接口文档-账号与权限最小demo.md`。
"""

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

# 允许的角色组合（1~2 个角色）；排序后比较，避免前端顺序影响结果
VALID_ROLE_COMBOS = {
    ("user",),
    ("admin",),
    ("super_admin",),
    ("admin", "user"),
    ("super_admin", "user"),
}

# 角色固定展示顺序：普通用户 -> 管理员 -> 超管
ROLE_ORDER = {"user": 0, "admin": 1, "super_admin": 2}

# 权限点分组顺序：用户端在前，管理后台在后
GROUP_ORDER = {"用户端": 0, "管理后台": 1}


def _roles_of(user: User) -> set[str]:
    return {role.code for role in user.roles}


def _is_super(user: User) -> bool:
    return "super_admin" in _roles_of(user)


def _role_objects(db: Session, codes: list[str]) -> list[Role]:
    return list(db.scalars(select(Role).where(Role.code.in_(codes))))


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


def _catalog_sorted(permissions: list[Permission]) -> list[Permission]:
    """按 6 号文档要求：先分组（用户端、管理后台），再按权限码排序。"""
    return sorted(permissions, key=lambda p: (GROUP_ORDER.get(p.group_name or "", 99), p.code))


def _permission_codes_of(role: Role, catalog: list[Permission]) -> list[str]:
    owned = {permission.code for permission in role.permissions}
    if role.code == "super_admin":
        return [permission.code for permission in catalog]
    return [permission.code for permission in catalog if permission.code in owned]


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ApiError(400, 10003, "创建时间范围不合法") from None
    return datetime.combine(day, time.min, tzinfo=settings.TZ).astimezone(timezone.utc)


def _fail(
    db: Session,
    request: Request,
    auth: AuthContext,
    *,
    action: str,
    target_type: str | None,
    target_id: str | None,
    status_code: int,
    code: int,
    message: str,
) -> None:
    """记录失败操作日志（独立事务）后抛出业务异常。

    接口文档 §2.5 要求业务失败记录 result=failed 与原因；失败日志不能与
    业务操作同事务回滚，因此先 rollback 再单独提交。
    """
    db.rollback()
    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action=action,
        result="failed",
        detail={"reason": message},
        target_type=target_type,
        target_id=target_id,
    )
    db.commit()
    raise ApiError(status_code, code, message)


def _get_target_user(
    db: Session,
    user_id: int,
    request: Request,
    auth: AuthContext,
    *,
    action: str,
) -> User:
    """读取目标账号；不存在时写失败审计并返回 404/30017。"""
    user = db.get(User, user_id)
    if user is None:
        _fail(
            db,
            request,
            auth,
            action=action,
            target_type="account",
            target_id=str(user_id),
            status_code=404,
            code=30017,
            message="用户不存在",
        )
    return user


@router.get("/users")
def list_users(
    keyword: str | None = None,
    role: str | None = None,
    status: str = "all",
    created_from: str | None = None,
    created_to: str | None = None,
    page: int = Query(1),
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
    # 接口文档 §1.5：page 小于 1 按 1 处理
    page = max(1, page)

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
    request: Request,
    payload: CreateUserRequest | None = None,
    auth: AuthContext = Depends(require_permission("admin.accounts.create")),
    db: Session = Depends(get_db),
) -> dict:
    """新建账号。"""
    # 无请求体时也返回文档约定的 10002，而不是框架 422
    payload = payload or CreateUserRequest()
    action = "account.create"
    username = (payload.username or "").strip()
    display_name = (payload.display_name or "").strip()
    password = payload.password or ""
    status = payload.status or "active"
    target_id = username or None

    def fail(status_code: int, code: int, message: str) -> None:
        _fail(
            db,
            request,
            auth,
            action=action,
            target_type="account",
            target_id=target_id,
            status_code=status_code,
            code=code,
            message=message,
        )

    if not username or not display_name or not password or payload.roles is None:
        fail(400, 10002, "请填写完整账号信息")
    # 接口文档 §5.1：密码不可为纯空格
    if not password.strip():
        fail(400, 10002, "请填写完整账号信息")
    if not USERNAME_RE.fullmatch(username):
        fail(400, 10003, "用户名需为 4~20 位字母、数字或下划线")
    if len(display_name) > 30:
        fail(400, 10004, "显示名不能超过 30 个字符")
    if not (8 <= len(password) <= 32):
        fail(400, 10004, "密码长度需为 8~32 位")
    if status not in ("active", "disabled"):
        fail(400, 10003, "状态参数不合法")

    try:
        combo = _validate_role_combo(payload.roles)
    except ApiError as exc:
        fail(exc.status_code, exc.code, exc.message)

    if "super_admin" in combo and not _is_super(auth.user):
        fail(403, 20005, "无权分配超管角色")

    if db.scalar(select(User).where(User.username == username)) is not None:
        fail(409, 30010, "用户名已存在")

    user = User(
        username=username,
        display_name=display_name,
        password_hash=hash_password(password),
        status=status,
    )
    user.roles = _role_objects(db, list(combo))
    db.add(user)
    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action=action,
        result="success",
        detail={"target_username": username},
        target_type="account",
        target_id=username,
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
    target = db.get(User, user_id)
    if target is None:
        raise ApiError(404, 30017, "用户不存在")
    if not _is_super(auth.user) and _is_super(target):
        raise ApiError(403, 20006, "无权操作超管账号")
    return ok(_user_payload(db, target))


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    request: Request,
    payload: UpdateUserRequest | None = None,
    auth: AuthContext = Depends(require_permission("admin.accounts.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """编辑显示名、角色、状态。"""
    # 无请求体时按「请至少修改一个字段」返回 10002
    payload = payload or UpdateUserRequest()
    action = "account.update"
    target = _get_target_user(db, user_id, request, auth, action=action)

    def fail(status_code: int, code: int, message: str) -> None:
        _fail(
            db,
            request,
            auth,
            action=action,
            target_type="account",
            target_id=target.username,
            status_code=status_code,
            code=code,
            message=message,
        )

    actor_is_super = _is_super(auth.user)
    is_self = auth.user.id == target.id

    # 请求中出现的字段（用于「至少修改一个字段」校验）
    if payload.display_name is None and payload.roles is None and payload.status is None:
        fail(400, 10002, "请至少修改一个字段")

    # 已删除账号必须先走恢复接口，不能通过编辑绕过（接口文档 §13.1）
    if target.status == "deleted":
        fail(409, 30018, "当前账号状态不允许该操作")

    # 按「值是否改变」判断边界：前端编辑弹窗总是提交 display_name/roles/status
    roles_changed = payload.roles is not None and set(payload.roles) != _roles_of(target)
    status_changed = payload.status is not None and payload.status != target.status

    # 账号边界（接口文档 §7.2）
    if not actor_is_super and _is_super(target):
        fail(403, 20006, "无权操作超管账号")
    if is_self and not actor_is_super and (roles_changed or status_changed):
        fail(403, 20007, "不能修改自己的角色或状态")
    if is_self and actor_is_super:
        if status_changed:
            fail(403, 20007, "不能修改自己的状态")
        if roles_changed and "super_admin" not in (payload.roles or []):
            fail(403, 20007, "不能移除自己的超管角色")
    if not actor_is_super and not is_self and "admin" in _roles_of(target) and roles_changed:
        fail(403, 20005, "无权修改其他管理员的角色")
    if not actor_is_super and roles_changed and "super_admin" in (payload.roles or []):
        fail(403, 20005, "无权分配超管角色")

    before = {
        "display_name": target.display_name,
        "roles": sorted(_roles_of(target)),
        "status": target.status,
    }

    new_display_name = target.display_name
    new_status = target.status
    new_roles = _roles_of(target)

    if payload.display_name is not None:
        dn = payload.display_name.strip()
        if not dn:
            fail(400, 10002, "请填写完整账号信息")
        if len(dn) > 30:
            fail(400, 10004, "显示名不能超过 30 个字符")
        new_display_name = dn
    if payload.roles is not None:
        try:
            combo = _validate_role_combo(payload.roles)
        except ApiError as exc:
            fail(exc.status_code, exc.code, exc.message)
        new_roles = set(combo)
    if payload.status is not None:
        if payload.status not in ("active", "disabled"):
            fail(400, 10003, "状态参数不合法")
        new_status = payload.status

    # 最后可用超管保护（接口文档 §7.2 / §13）
    if _is_super(target) and target.status == "active":
        losing_super = (roles_changed and "super_admin" not in new_roles) or (
            status_changed and new_status != "active"
        )
        if losing_super and _count_active_super(db) <= 1:
            fail(409, 30011, "必须保留至少一个可用超管")

    target.display_name = new_display_name
    if roles_changed:
        target.roles = _role_objects(db, list(new_roles))
    if status_changed:
        target.status = new_status
        # 禁用使已签发 token 失效；启用不再恢复旧 token
        if new_status == "disabled":
            target.token_version += 1

    after = {
        "display_name": target.display_name,
        "roles": sorted(new_roles),
        "status": target.status,
    }
    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action=action,
        result="success",
        detail={"before": before, "after": after},
        target_type="account",
        target_id=target.username,
    )
    db.commit()
    db.refresh(target)
    return ok(_user_payload(db, target))


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    request: Request,
    payload: ResetPasswordRequest | None = None,
    auth: AuthContext = Depends(require_permission("admin.accounts.reset_password")),
    db: Session = Depends(get_db),
) -> dict:
    """重置密码，token_version 递增使旧 token 失效。"""
    # 无请求体时返回 10002「请输入新密码」
    payload = payload or ResetPasswordRequest()
    action = "account.reset_password"
    target = _get_target_user(db, user_id, request, auth, action=action)

    def fail(status_code: int, code: int, message: str) -> None:
        _fail(
            db,
            request,
            auth,
            action=action,
            target_type="account",
            target_id=target.username,
            status_code=status_code,
            code=code,
            message=message,
        )

    new_password = (payload.new_password or "").strip()
    if not new_password:
        fail(400, 10002, "请输入新密码")
    if not (8 <= len(new_password) <= 32):
        fail(400, 10004, "密码长度需为 8~32 位")

    if not _is_super(auth.user) and _is_super(target):
        fail(403, 20006, "无权操作超管账号")
    if auth.user.id == target.id:
        fail(403, 20007, "请通过个人中心修改自己的密码")

    target.password_hash = hash_password(new_password)
    target.token_version += 1
    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action=action,
        result="success",
        detail={"user_id": target.id, "username": target.username},
        target_type="account",
        target_id=target.username,
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
    action = "account.disable"
    target = _get_target_user(db, user_id, request, auth, action=action)

    def fail(status_code: int, code: int, message: str) -> None:
        _fail(
            db,
            request,
            auth,
            action=action,
            target_type="account",
            target_id=target.username,
            status_code=status_code,
            code=code,
            message=message,
        )

    if not _is_super(auth.user) and _is_super(target):
        fail(403, 20006, "无权操作超管账号")
    if auth.user.id == target.id:
        fail(403, 20007, "不能对自己执行该操作")
    if target.status == "deleted":
        fail(409, 30018, "当前账号状态不允许该操作")
    if target.status == "disabled":
        return ok(_user_payload(db, target))
    if _is_super(target) and _count_active_super(db) <= 1:
        fail(409, 30011, "必须保留至少一个可用超管")

    target.status = "disabled"
    target.token_version += 1
    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action=action,
        result="success",
        detail={"target_username": target.username},
        target_type="account",
        target_id=target.username,
    )
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
    action = "account.enable"
    target = _get_target_user(db, user_id, request, auth, action=action)

    def fail(status_code: int, code: int, message: str) -> None:
        _fail(
            db,
            request,
            auth,
            action=action,
            target_type="account",
            target_id=target.username,
            status_code=status_code,
            code=code,
            message=message,
        )

    if not _is_super(auth.user) and _is_super(target):
        fail(403, 20006, "无权操作超管账号")
    if target.status == "deleted":
        fail(409, 30018, "当前账号状态不允许该操作")
    if target.status == "active":
        return ok(_user_payload(db, target))

    target.status = "active"
    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action=action,
        result="success",
        detail={"target_username": target.username},
        target_type="account",
        target_id=target.username,
    )
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
    action = "account.delete"
    target = _get_target_user(db, user_id, request, auth, action=action)

    def fail(status_code: int, code: int, message: str) -> None:
        _fail(
            db,
            request,
            auth,
            action=action,
            target_type="account",
            target_id=target.username,
            status_code=status_code,
            code=code,
            message=message,
        )

    if not _is_super(auth.user) and _is_super(target):
        fail(403, 20006, "无权操作超管账号")
    if auth.user.id == target.id:
        fail(403, 20007, "不能对自己执行该操作")
    if target.status == "deleted":
        fail(409, 30018, "当前账号状态不允许该操作")
    if _is_super(target) and target.status == "active" and _count_active_super(db) <= 1:
        fail(409, 30011, "必须保留至少一个可用超管")

    target.status = "deleted"
    target.deleted_at = datetime.now(timezone.utc)
    target.token_version += 1
    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action=action,
        result="success",
        detail={"target_username": target.username},
        target_type="account",
        target_id=target.username,
    )
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
    action = "account.restore"
    target = _get_target_user(db, user_id, request, auth, action=action)

    def fail(status_code: int, code: int, message: str) -> None:
        _fail(
            db,
            request,
            auth,
            action=action,
            target_type="account",
            target_id=target.username,
            status_code=status_code,
            code=code,
            message=message,
        )

    if not _is_super(auth.user) and _is_super(target):
        fail(403, 20006, "无权操作超管账号")
    if target.status != "deleted":
        fail(409, 30018, "当前账号状态不允许该操作")

    target.status = "active"
    target.deleted_at = None
    target.token_version += 1
    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action=action,
        result="success",
        detail={"target_username": target.username},
        target_type="account",
        target_id=target.username,
    )
    db.commit()
    return ok(_user_payload(db, target))


@router.get("/roles")
def list_roles(
    auth: AuthContext = Depends(require_permission("admin.roles.view")),
    db: Session = Depends(get_db),
) -> dict:
    """三个角色与权限点目录。"""
    roles = sorted(db.scalars(select(Role)), key=lambda r: ROLE_ORDER.get(r.code, 99))
    catalog = _catalog_sorted(list(db.scalars(select(Permission))))
    return ok(
        {
            "roles": [
                {
                    "code": role.code,
                    "name": role.name,
                    "editable": role.code != "super_admin",
                    "permissions": _permission_codes_of(role, catalog),
                }
                for role in roles
            ],
            "permissions": [
                {
                    "code": p.code,
                    "name": p.name,
                    "type": p.type,
                    "group_name": p.group_name,
                    "is_super_only": p.is_super_only,
                }
                for p in catalog
            ],
        }
    )


@router.put("/roles/{code}/permissions")
def update_role_permissions(
    code: str,
    request: Request,
    payload: RolePermissionsRequest | None = None,
    auth: AuthContext = Depends(require_permission("admin.roles.edit")),
    db: Session = Depends(get_db),
) -> dict:
    """保存角色权限点（仅超管）。"""
    action = "role.update"

    def fail(status_code: int, code_value: int, message: str) -> None:
        _fail(
            db,
            request,
            auth,
            action=action,
            target_type="role",
            target_id=code,
            status_code=status_code,
            code=code_value,
            message=message,
        )

    if code == "super_admin":
        fail(403, 20005, "超管角色权限不可编辑")
    if code not in ("user", "admin"):
        fail(400, 10003, "角色参数不合法")
    if payload is None or payload.permissions is None:
        fail(400, 10002, "请选择权限点")

    # 重复权限码去重，保持请求顺序
    requested = list(dict.fromkeys(payload.permissions))
    catalog = _catalog_sorted(list(db.scalars(select(Permission))))
    known = {p.code for p in catalog}
    unknown = [c for c in requested if c not in known]
    if unknown:
        fail(400, 10003, "权限点不存在")

    super_only = {p.code for p in catalog if p.is_super_only}
    if any(c in super_only for c in requested):
        fail(409, 30015, "超管专属权限点不能授予该角色")

    # 最低权限校验（接口文档 §10.2 规则 4）
    if code == "user" and "user.workspace" not in requested:
        fail(409, 30015, "普通用户角色至少保留「创作台」")
    if code == "admin" and "admin.dashboard.view" not in requested:
        fail(409, 30015, "管理员角色至少保留「概览」")

    role = db.scalar(select(Role).where(Role.code == code))
    if role is None:
        fail(400, 10003, "角色参数不合法")

    before = _permission_codes_of(role, catalog)
    requested_set = set(requested)
    role.permissions = [p for p in catalog if p.code in requested_set]
    after = _permission_codes_of(role, catalog)

    write_audit(
        db,
        request,
        user_id=auth.user.id,
        username_snapshot=auth.user.username,
        action=action,
        result="success",
        detail={"before": before, "after": after},
        target_type="role",
        target_id=code,
    )
    db.commit()
    return ok(
        {
            "code": role.code,
            "name": role.name,
            "editable": True,
            "permissions": after,
        }
    )
