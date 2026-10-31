"""幂等种子（10 号 §10.2 / 接口文档 §4.2）。

写入 3 个角色、23 个权限点、角色权限矩阵、4 条尺寸预设、8 条系统提示词与版本 1、
1 条启用的模型配置。连续执行两次第二次不新增行，已修改的数据不被覆盖。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import ModelConfig, PromptVersion, SizePreset, SystemPrompt
from app.models.user import Permission, Role, role_permissions

# (code, name)
ROLES: list[tuple[str, str]] = [
    ("user", "普通用户"),
    ("admin", "管理员"),
    ("super_admin", "超管"),
]

# (code, name, type, group_name, is_super_only, description)
PERMISSIONS: list[tuple[str, str, str, str, bool, str]] = [
    ("user.workspace", "创作台", "menu", "用户端", False, "进入创作工作台"),
    ("user.generate", "发起生成", "action", "用户端", False, "上传商品图并生成示例图与全套图"),
    ("user.history", "历史作品", "menu", "用户端", False, "查看历史作品"),
    ("user.profile", "个人中心", "menu", "用户端", False, "进入个人中心"),
    ("admin.dashboard.view", "概览", "menu", "统计分析", False, "查看管理后台概览"),
    ("admin.accounts.view", "用户管理", "menu", "账号与权限", False, "查看用户列表"),
    ("admin.accounts.create", "新建账号", "action", "账号与权限", False, "新建账号"),
    ("admin.accounts.edit", "编辑账号", "action", "账号与权限", False, "编辑账号"),
    ("admin.accounts.reset_password", "重置密码", "action", "账号与权限", False, "重置用户密码"),
    ("admin.accounts.disable", "禁用/启用", "action", "账号与权限", False, "禁用/启用账号"),
    ("admin.accounts.delete", "删除/恢复", "action", "账号与权限", False, "软删除/恢复账号"),
    ("admin.roles.view", "角色管理", "menu", "账号与权限", True, "查看角色与权限点（仅超管）"),
    ("admin.roles.edit", "编辑权限点", "action", "账号与权限", True, "编辑角色权限点（仅超管）"),
    ("admin.content.view", "内容追溯", "menu", "内容追溯", False, "查看聊天与生图记录"),
    ("admin.assets.view", "素材与模板", "menu", "素材与模板", False, "查看模板/素材/尺寸"),
    ("admin.assets.edit", "编辑素材/模板/尺寸", "action", "素材与模板", False, "编辑模板/素材/尺寸"),
    ("admin.prompts.view", "系统提示词", "menu", "Agent 配置", False, "查看系统提示词"),
    ("admin.prompts.edit", "编辑系统提示词", "action", "Agent 配置", False, "编辑系统提示词"),
    ("admin.model.view", "模型配置", "menu", "Agent 配置", True, "查看模型配置（仅超管）"),
    ("admin.model.edit", "编辑模型配置", "action", "Agent 配置", True, "编辑模型配置（仅超管）"),
    ("admin.tokens.view", "Token 统计", "menu", "统计分析", False, "查看 Token 统计"),
    ("admin.audit.view", "操作日志", "menu", "统计分析", True, "查看操作日志（仅超管）"),
    ("admin.export", "数据导出", "action", "数据导出", True, "导出数据（仅超管）"),
]

# 角色权限矩阵
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
    "super_admin": [permission[0] for permission in PERMISSIONS],
}

# (platform_name, width, height, sort_order)
SIZE_PRESETS: list[tuple[str, int, int, int]] = [
    ("淘宝/天猫", 1000, 1000, 0),
    ("京东", 1000, 1000, 1),
    ("拼多多", 1000, 1000, 2),
    ("抖音", 1000, 1000, 3),
]

# (agent_code, name, content)
AGENTS: list[tuple[str, str, str]] = [
    ("planner", "规划 Agent", "你是电商图的规划 Agent，负责拆解用户需求为 1 张主图 + 5 张详情图的生成计划。"),
    ("product_understanding", "商品理解 Agent", "你是商品理解 Agent，负责从商品名称与上传图推断类目、卖点、人群与场景。"),
    ("copywriter", "文案 Agent", "你是文案 Agent，负责为商品图生成标题、卖点与说明文案。"),
    ("prompt_builder", "提示词 Agent", "你是提示词 Agent，负责把文案与风格转换为结构化的生图提示词并预留文字区。"),
    ("image_generator", "生图执行 Agent", "你是生图执行 Agent，负责调用图像模型完成图生图/文生图。"),
    ("quality_reviewer", "质量审核 Agent", "你是质量审核 Agent，负责检查文字错乱、主体变形与合规问题。"),
    ("repairer", "修复 Agent", "你是修复 Agent，负责根据审核问题修正提示词并触发重新生成。"),
    ("platform_rule", "平台规范 Agent", "你是平台规范 Agent，负责校验尺寸、违禁词与类目规则。"),
]


def seed(db: Session) -> dict[str, int]:
    """执行幂等种子，返回各实体新增行数。"""
    inserted = {
        "roles": 0,
        "permissions": 0,
        "role_permissions": 0,
        "size_presets": 0,
        "system_prompts": 0,
        "prompt_versions": 0,
        "model_configs": 0,
    }

    # 1. 角色
    roles: dict[str, Role] = {}
    for code, name in ROLES:
        role = db.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(code=code, name=name, is_system=True)
            db.add(role)
            db.flush()
            inserted["roles"] += 1
        roles[code] = role

    # 2. 权限点
    permissions: dict[str, Permission] = {}
    for code, name, type_, group_name, is_super_only, description in PERMISSIONS:
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
            inserted["permissions"] += 1
        permissions[code] = permission

    # 3. 角色权限矩阵：只补缺失行，不删除已有行
    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        role = roles[role_code]
        existing = {
            permission.code
            for permission in db.scalars(
                select(Permission)
                .join(role_permissions, role_permissions.c.permission_id == Permission.id)
                .where(role_permissions.c.role_id == role.id)
            )
        }
        for permission_code in permission_codes:
            if permission_code not in existing:
                db.execute(
                    role_permissions.insert().values(
                        role_id=role.id, permission_id=permissions[permission_code].id
                    )
                )
                inserted["role_permissions"] += 1

    # 4. 尺寸预设
    for platform_name, width, height, sort_order in SIZE_PRESETS:
        existing = db.scalar(
            select(SizePreset).where(
                SizePreset.platform_name == platform_name,
                SizePreset.width == width,
                SizePreset.height == height,
            )
        )
        if existing is None:
            db.add(
                SizePreset(
                    platform_name=platform_name,
                    width=width,
                    height=height,
                    sort_order=sort_order,
                )
            )
            inserted["size_presets"] += 1

    # 5. 系统提示词与版本 1
    for agent_code, name, content in AGENTS:
        prompt = db.scalar(select(SystemPrompt).where(SystemPrompt.agent_code == agent_code))
        if prompt is None:
            prompt = SystemPrompt(
                agent_code=agent_code, name=name, content=content, current_version=1
            )
            db.add(prompt)
            db.flush()
            inserted["system_prompts"] += 1
        # 版本 1 缺失时补写，内容取当前 content，不修改提示词本身
        version = db.scalar(
            select(PromptVersion).where(
                PromptVersion.prompt_id == prompt.id, PromptVersion.version == 1
            )
        )
        if version is None:
            db.add(
                PromptVersion(
                    prompt_id=prompt.id,
                    agent_code=agent_code,
                    version=1,
                    content=prompt.content,
                )
            )
            inserted["prompt_versions"] += 1

    # 6. 模型配置：没有启用配置时插入默认配置
    active = db.scalar(select(ModelConfig).where(ModelConfig.is_active.is_(True)))
    if active is None:
        db.add(
            ModelConfig(
                provider="volcengine_ark",
                base_url="https://ark.cn-beijing.volces.com/api/v3",
                api_key_ciphertext=None,
                text_model="doubao-seed-character-demo",
                image_model="doubao-seedream-demo",
                vision_model=None,
                temperature=0.7,
                timeout_seconds=120,
                concurrency=4,
                retry_count=1,
                max_context_tokens=32000,
                is_active=True,
            )
        )
        inserted["model_configs"] += 1

    db.commit()
    return inserted
