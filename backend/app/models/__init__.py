"""共享 ORM 模型汇总。

导入本包即可把所有模型注册到 Base.metadata，供建表与种子脚本使用。
"""

from app.models.audit import AuditLog
from app.models.user import Permission, Role, User, role_permissions, user_roles
from app.models.workspace import (
    AgentRun,
    ChatMessage,
    CreativeSession,
    GeneratedImage,
    GenerationBatch,
    UploadedAsset,
)

__all__ = [
    "AgentRun",
    "AuditLog",
    "ChatMessage",
    "CreativeSession",
    "GeneratedImage",
    "GenerationBatch",
    "Permission",
    "Role",
    "UploadedAsset",
    "User",
    "role_permissions",
    "user_roles",
]
