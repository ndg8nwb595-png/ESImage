"""种子数据定义与幂等写入逻辑。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import Permission, Role, User

DEMO_PASSWORD = "Demo1234"

# 权限点：(code, 名称, 类型, 分组, 是否仅超管, 说明)
PERMISSIONS: list[tuple[str, str, str, str | None, bool, str]] = [
    ("user.workspace", "创作台", "menu", "用户端", False, "进入创作工作台"),
    ("user.generate", "生成图片", "action", "用户端", False, "上传商品图、生成示例图与全套图"),
    ("user.history", "历史作品", "menu", "用户端", False, "查看历史作品"),
    ("user.profile", "个人中心", "menu", "用户端", False, "进入个人中心"),
    ("admin.dashboard.view", "管理概览", "menu", "概览", False, "查看管理后台概览"),
    ("admin.tokens.view", "Token 统计", "menu", "概览", False, "查看 Token 统计"),
    ("admin.accounts.view", "用户列表", "menu", "账号与权限", False, "查看用户列表"),
    ("admin.accounts.create", "新建账号", "action", "账号与权限", False, "新建账号"),
    ("admin.accounts.edit", "编辑账号", "action", "账号与权限", False, "编辑账号"),
    ("admin.accounts.reset_password", "重置密码", "action", "账号与权限", False, "重置用户密码"),
    ("admin.accounts.disable", "禁用/启用", "action", "账号与权限", False, "禁用/启用账号"),
    ("admin.accounts.delete", "删除/恢复", "action", "账号与权限", False, "软删除/恢复账号"),
    ("admin.roles.view", "角色查看", "menu", "账号与权限", True, "查看角色与权限点（仅超管）"),
    ("admin.roles.edit", "角色编辑", "action", "账号与权限", True, "编辑角色权限点（仅超管）"),
    ("admin.content.view", "内容追溯", "menu", "内容追溯", False, "查看聊天与生图记录"),
    ("admin.assets.view", "素材模板查看", "menu", "素材与模板", False, "查看模板/素材/尺寸"),
    ("admin.assets.edit", "素材模板编辑", "action", "素材与模板", False, "编辑模板/素材/尺寸"),
    ("admin.prompts.view", "提示词查看", "menu", "Agent 配置", False, "查看系统提示词"),
    ("admin.prompts.edit", "提示词编辑", "action", "Agent 配置", False, "编辑系统提示词"),
    ("admin.model.view", "模型配置查看", "menu", "Agent 配置", True, "查看模型配置（仅超管）"),
    ("admin.model.edit", "模型配置编辑", "action", "Agent 配置", True, "编辑模型配置（仅超管）"),
    ("admin.audit.view", "操作日志", "menu", "操作日志", True, "查看操作日志（仅超管）"),
    ("admin.export", "数据导出", "action", "操作日志", True, "导出数据（仅超管）"),
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
    "super_admin": [
        "user.workspace",
        "user.generate",
        "user.history",
        "user.profile",
        "admin.dashboard.view",
        "admin.tokens.view",
        "admin.accounts.view",
        "admin.accounts.create",
        "admin.accounts.edit",
        "admin.accounts.reset_password",
        "admin.accounts.disable",
        "admin.accounts.delete",
        "admin.roles.view",
        "admin.roles.edit",
        "admin.content.view",
        "admin.assets.view",
        "admin.assets.edit",
        "admin.prompts.view",
        "admin.prompts.edit",
        "admin.model.view",
        "admin.model.edit",
        "admin.audit.view",
        "admin.export",
    ],
}

ROLES: list[tuple[str, str]] = [
    ("user", "普通用户"),
    ("admin", "管理员"),
    ("super_admin", "超管"),
]

# (用户名, 显示名, 角色码列表)
DEMO_USERS: list[tuple[str, str, list[str]]] = [
    ("demo_user", "演示用户", ["user"]),
    ("demo_admin", "演示管理员", ["admin"]),
    ("demo_dual", "双角色演示", ["user", "admin"]),
    # 8 号聊天记录 / 模型配置演示账号
    ("demo_super", "演示超管", ["super_admin"]),
]


def _ensure_role(db: Session, code: str, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.code == code))
    if role is None:
        role = Role(code=code, name=name, is_system=True)
        db.add(role)
        db.flush()
        print(f"[种子] 新建角色 {code}")
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
