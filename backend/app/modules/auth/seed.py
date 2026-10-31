"""种子数据定义与幂等写入逻辑。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import Permission, Role, User

DEMO_PASSWORD = "Demo1234"

# 权限点：(code, 名称, 类型, 分组, 是否仅超管, 说明)
# 名称、类型与分组对齐 6 号接口文档 §2.3；分组只有「用户端 / 管理后台」两类。
PERMISSIONS: list[tuple[str, str, str, str | None, bool, str]] = [
    ("user.workspace", "创作台", "menu", "用户端", False, "进入创作工作台"),
    ("user.generate", "发起生成", "action", "用户端", False, "上传商品图、发起示例图与全套图生成"),
    ("user.history", "历史作品", "menu", "用户端", False, "查看历史作品"),
    ("user.profile", "个人中心", "menu", "用户端", False, "进入个人中心"),
    ("admin.dashboard.view", "概览", "menu", "管理后台", False, "查看管理后台概览"),
    ("admin.accounts.view", "用户管理", "menu", "管理后台", False, "查看用户列表与详情"),
    ("admin.accounts.create", "新建账号", "action", "管理后台", False, "新建账号"),
    ("admin.accounts.edit", "编辑账号", "action", "管理后台", False, "编辑显示名、角色与状态"),
    ("admin.accounts.reset_password", "重置密码", "action", "管理后台", False, "重置用户密码"),
    ("admin.accounts.disable", "禁用/启用", "action", "管理后台", False, "禁用或启用账号"),
    ("admin.accounts.delete", "删除/恢复", "action", "管理后台", False, "软删除或恢复账号"),
    ("admin.roles.view", "角色管理", "menu", "管理后台", True, "查看角色与权限点（仅超管）"),
    ("admin.roles.edit", "编辑权限点", "action", "管理后台", True, "编辑角色权限点（仅超管）"),
    ("admin.content.view", "内容追溯", "menu", "管理后台", False, "查看聊天与生图记录"),
    ("admin.assets.view", "素材与模板", "menu", "管理后台", False, "查看模板、素材与尺寸"),
    ("admin.assets.edit", "编辑素材/模板/尺寸", "action", "管理后台", False, "编辑模板、素材与尺寸"),
    ("admin.prompts.view", "系统提示词", "menu", "管理后台", False, "查看系统提示词"),
    ("admin.prompts.edit", "编辑系统提示词", "action", "管理后台", False, "编辑系统提示词"),
    ("admin.model.view", "模型配置", "menu", "管理后台", True, "查看模型配置（仅超管）"),
    ("admin.model.edit", "编辑模型配置", "action", "管理后台", True, "编辑模型配置（仅超管）"),
    ("admin.tokens.view", "Token 统计", "menu", "管理后台", False, "查看 Token 统计"),
    ("admin.audit.view", "操作日志", "menu", "管理后台", True, "查看操作日志（仅超管）"),
    ("admin.export", "数据导出", "action", "管理后台", True, "导出数据（仅超管）"),
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "user": ["user.workspace", "user.generate", "user.history", "user.profile"],
    "admin": [
        "admin.dashboard.view",
        "admin.tokens.view",
        "admin.accounts.view",
        "admin.accounts.create",
        "admin.accounts.edit",
        "admin.accounts.reset_password",
        "admin.accounts.disable",
        "admin.accounts.delete",
        "admin.content.view",
        "admin.assets.view",
        "admin.assets.edit",
        "admin.prompts.view",
        "admin.prompts.edit",
    ],
    # 超管不写 role_permissions 行：由鉴权层按角色即时授予全部 23 个权限码（6 号文档 §1.4）。
}

ROLES: list[tuple[str, str]] = [
    ("user", "普通用户"),
    ("admin", "管理员"),
    ("super_admin", "超管"),
]

# (用户名, 显示名, 角色码列表)
DEMO_USERS: list[tuple[str, str, list[str]]] = [
    ("demo_super", "演示超管", ["super_admin"]),
    ("demo_user", "演示用户", ["user"]),
    ("demo_user2", "演示用户二", ["user"]),
    ("demo_admin", "演示管理员", ["admin"]),
    ("demo_dual", "双角色演示", ["user", "admin"]),
]


def _ensure_role(db: Session, code: str, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.code == code))
    if role is None:
        role = Role(code=code, name=name, is_system=True)
        db.add(role)
        db.flush()
        print(f"[种子] 新建角色 {code}")
    elif role.name != name:
        # 固定角色的中文名属于系统目录，允许种子收敛；不触碰用户与权限配置
        role.name = name
        print(f"[种子] 更新角色名称 {code}: {name}")
    return role


def _ensure_permission(
    db: Session,
    code: str,
    name: str,
    type_: str,
    group_name: str | None,
    is_super_only: bool,
    description: str,
) -> Permission:
    permission = db.scalar(select(Permission).where(Permission.code == code))
    if permission is None:
        permission = Permission(
            code=code,
            name=name,
            type=type_,
            group_name=group_name,
            is_super_only=is_super_only,
            description=description,
        )
        db.add(permission)
        db.flush()
        print(f"[种子] 新建权限点 {code}")
    else:
        # 权限点是系统目录：已有库重跑种子时收敛名称/类型/分组，
        # 但不改密码、角色权限关联等用户配置；否则改名改分组永远不会生效。
        changed = (
            permission.name != name
            or permission.type != type_
            or permission.group_name != group_name
            or permission.is_super_only != is_super_only
            or permission.description != description
        )
        if changed:
            permission.name = name
            permission.type = type_
            permission.group_name = group_name
            permission.is_super_only = is_super_only
            permission.description = description
            print(f"[种子] 更新权限点 {code}")
    return permission


def _ensure_user(db: Session, username: str, display_name: str, role_codes: list[str]) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(DEMO_PASSWORD),
            status="active",
            token_version=0,
        )
        db.add(user)
        db.flush()
        print(f"[种子] 新建演示账号 {username}")
    else:
        print(f"[种子] 演示账号 {username} 已存在，跳过")

    existing_role_codes = {role.code for role in user.roles}
    for code in role_codes:
        if code not in existing_role_codes:
            role = db.scalar(select(Role).where(Role.code == code))
            if role is not None:
                user.roles.append(role)
                print(f"[种子] 账号 {username} 绑定角色 {code}")
    return user


def seed(db: Session) -> None:
    """执行幂等种子。已存在的数据不覆盖。"""
    # 1. 角色与权限点
    roles = {code: _ensure_role(db, code, name) for code, name in ROLES}
    permissions = {item[0]: _ensure_permission(db, *item) for item in PERMISSIONS}

    # 2. 角色-权限关联
    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        role = roles[role_code]
        existing = {permission.code for permission in role.permissions}
        for permission_code in permission_codes:
            if permission_code not in existing:
                role.permissions.append(permissions[permission_code])
                print(f"[种子] 角色 {role_code} 绑定权限 {permission_code}")

    # 3. 演示账号与用户-角色关联
    for username, display_name, role_codes in DEMO_USERS:
        _ensure_user(db, username, display_name, role_codes)

    db.commit()
