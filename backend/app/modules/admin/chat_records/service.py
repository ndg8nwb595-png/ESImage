"""8 号管理后台-聊天记录：查询、可见范围与序列化。

所有查询都在接口层过滤管理员可见范围（排除 super_admin 账号的会话），
不依赖前端隐藏。聊天相关接口只读，不修改业务数据。
"""

from __future__ import annotations

import re
from datetime import datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import AuthContext
from app.core.response import ApiError
from app.models.config import SystemPrompt
from app.models.user import Role, User
from app.models.workspace import (
    AgentRun,
    ChatMessage,
    CreativeSession,
    GenerationBatch,
)
from app.modules.workspace.service import to_iso

# 全局 9 个提示词变量（8 号接口文档 §2.6）
GLOBAL_PROMPT_VARIABLES: tuple[str, ...] = (
    "product_name",
    "params",
    "requirement_summary",
    "chat_summary",
    "product_profile",
    "plan",
    "copy_blocks",
    "review_issues",
    "platform_rules",
)

SNIPPET_RADIUS = 40
SNIPPET_MAX_LENGTH = 120
KEYWORD_MAX_LENGTH = 50


def is_super(user: User) -> bool:
    """是否超管。"""
    return any(role.code == "super_admin" for role in user.roles)


def escape_like(value: str) -> str:
    """转义 ILIKE 通配符，避免用户输入被当作 ``%`` / ``_``。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def ilike_pattern(value: str) -> str:
    """构造大小写不敏感的包含匹配模式，配合 ``escape="\\"`` 使用。"""
    return f"%{escape_like(value)}%"


def super_admin_user_ids():
    """拥有 super_admin 角色的用户 ID 子查询。"""
    return select(User.id).where(User.roles.any(Role.code == "super_admin"))


def visible_session_ids(auth: AuthContext):
    """当前角色可见的会话 ID 子查询；超管返回 None 表示不限制。"""
    if is_super(auth.user):
        return None
    return select(CreativeSession.id).where(
        ~CreativeSession.user_id.in_(super_admin_user_ids())
    )


def ensure_session_visible(db: Session, auth: AuthContext, session: CreativeSession) -> None:
    """管理员不能访问超管账号的会话，统一 403 20005。"""
    if is_super(auth.user):
        return
    owner = db.get(User, session.user_id)
    if owner is not None and is_super(owner):
        raise ApiError(403, 20005, "无权限")


def get_visible_session(
    db: Session, auth: AuthContext, session_id: int
) -> CreativeSession:
    """读取会话并校验可见范围；不存在返回 30013。"""
    session = db.get(CreativeSession, session_id)
    if session is None:
        raise ApiError(404, 30013, "会话不存在")
    ensure_session_visible(db, auth, session)
    return session


def agent_names(db: Session, agent_codes: set[str]) -> dict[str, str]:
    """批量读取 Agent 中文名；缺失时回退 agent_code。"""
    if not agent_codes:
        return {}
    rows = db.scalars(
        select(SystemPrompt).where(SystemPrompt.agent_code.in_(agent_codes))
    )
    names = {row.agent_code: row.name for row in rows}
    return {code: names.get(code, code) for code in agent_codes}


def session_summaries(
    db: Session, sessions: list[CreativeSession]
) -> list[dict]:
    """批量组装会话摘要，避免逐会话查询造成 N+1。"""
    if not sessions:
        return []

    session_ids = [session.id for session in sessions]
    user_ids = {session.user_id for session in sessions}

    users = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_(user_ids)))
    }
    message_counts = dict(
        db.execute(
            select(ChatMessage.session_id, func.count())
            .where(ChatMessage.session_id.in_(session_ids))
            .group_by(ChatMessage.session_id)
        ).all()
    )
    token_rows = db.execute(
        select(
            AgentRun.session_id,
            func.coalesce(func.sum(AgentRun.prompt_tokens), 0),
            func.coalesce(func.sum(AgentRun.completion_tokens), 0),
        )
        .where(AgentRun.session_id.in_(session_ids))
        .group_by(AgentRun.session_id)
    ).all()
    token_usage = {
        row[0]: (int(row[1]), int(row[2])) for row in token_rows
    }
    batch_counts = dict(
        db.execute(
            select(GenerationBatch.session_id, func.count())
            .where(GenerationBatch.session_id.in_(session_ids))
            .group_by(GenerationBatch.session_id)
        ).all()
    )

    items: list[dict] = []
    for session in sessions:
        user = users.get(session.user_id)
        prompt_tokens, completion_tokens = token_usage.get(session.id, (0, 0))
        items.append(
            {
                "session_id": session.id,
                "user": (
                    {
                        "user_id": user.id,
                        "username": user.username,
                        "display_name": user.display_name,
                    }
                    if user is not None
                    else None
                ),
                "title": session.title,
                "status": session.status,
                "message_count": int(message_counts.get(session.id, 0)),
                "last_message_at": to_iso(session.last_message_at),
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
                "batch_count": int(batch_counts.get(session.id, 0)),
                "created_at": to_iso(session.created_at),
                "updated_at": to_iso(session.updated_at),
            }
        )
    return items


def session_summary(db: Session, session: CreativeSession) -> dict:
    """单个会话摘要。"""
    return session_summaries(db, [session])[0]


def parse_day_range(
    value: str | None, *, field: str = "日期"
) -> tuple[datetime, datetime] | None:
    """把 ``YYYY-MM-DD`` 解析为东八区当天的 UTC 起止区间。"""
    if value is None or value.strip() == "":
        return None
    try:
        day = datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ApiError(400, 10003, f"{field}格式不合法") from None
    start = datetime.combine(day, time.min, tzinfo=settings.TZ)
    end = datetime.combine(day, time.max, tzinfo=settings.TZ)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def normalize_keyword(value: str | None, *, max_length: int = KEYWORD_MAX_LENGTH) -> str:
    """去除首尾空格；空串按未提供处理；超长返回 10004。"""
    keyword = (value or "").strip()
    if len(keyword) > max_length:
        raise ApiError(400, 10004, f"关键词不能超过 {max_length} 个字符")
    return keyword


def build_snippet(content: str, keyword: str) -> str:
    """截取关键词附近的纯文本摘要，折叠空白并加省略号。"""
    folded = re.sub(r"\s+", " ", content or "").strip()
    if not folded:
        return ""
    index = folded.lower().find(keyword.lower())
    if index < 0:
        index = 0

    start = max(0, index - SNIPPET_RADIUS)
    end = min(len(folded), index + len(keyword) + SNIPPET_RADIUS)
    piece = folded[start:end]

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(folded) else ""
    budget = SNIPPET_MAX_LENGTH - len(prefix) - len(suffix)
    if len(piece) > budget:
        piece = piece[:budget]
        suffix = "…"
    return f"{prefix}{piece}{suffix}"
