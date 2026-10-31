"""用户列表/详情的真实统计聚合。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import AgentRun, CreativeSession, GeneratedImage, GenerationBatch
from app.modules.admin.service import to_iso


def _counted_token_condition():
    """与 Token 统计一致的计入口径。"""
    return or_(
        AgentRun.status == "success",
        and_(
            AgentRun.status == "failed",
            (AgentRun.prompt_tokens + AgentRun.completion_tokens) > 0,
        ),
    )


def build_user_stats(db: Session, user_ids: list[int]) -> dict[int, dict[str, Any]]:
    """批量聚合用户统计，避免逐用户 N+1。"""
    if not user_ids:
        return {}

    image_counts = dict(
        db.execute(
            select(GeneratedImage.user_id, func.count())
            .where(
                GeneratedImage.user_id.in_(user_ids),
                GeneratedImage.image_type == "final",
                GeneratedImage.status == "success",
            )
            .group_by(GeneratedImage.user_id)
        ).all()
    )

    session_counts = dict(
        db.execute(
            select(CreativeSession.user_id, func.count())
            .where(CreativeSession.user_id.in_(user_ids))
            .group_by(CreativeSession.user_id)
        ).all()
    )

    failed_counts = dict(
        db.execute(
            select(GenerationBatch.user_id, func.count())
            .where(
                GenerationBatch.user_id.in_(user_ids),
                GenerationBatch.status.in_(("failed", "partially_failed")),
            )
            .group_by(GenerationBatch.user_id)
        ).all()
    )

    # Token 归属：优先会话，其次批次
    owner_user_id = func.coalesce(
        CreativeSession.user_id, GenerationBatch.user_id
    ).label("owner_user_id")
    token_rows = db.execute(
        select(
            owner_user_id,
            func.coalesce(
                func.sum(AgentRun.prompt_tokens + AgentRun.completion_tokens), 0
            ).label("token_total"),
        )
        .select_from(AgentRun)
        .join(CreativeSession, AgentRun.session_id == CreativeSession.id, isouter=True)
        .join(GenerationBatch, AgentRun.batch_id == GenerationBatch.id, isouter=True)
        .where(owner_user_id.in_(user_ids), _counted_token_condition())
        .group_by(owner_user_id)
    ).all()
    token_totals = {row.owner_user_id: int(row.token_total or 0) for row in token_rows}

    return {
        user_id: {
            "image_count": int(image_counts.get(user_id, 0)),
            "session_count": int(session_counts.get(user_id, 0)),
            "token_total": int(token_totals.get(user_id, 0)),
            "failed_task_count": int(failed_counts.get(user_id, 0)),
            "stats_available": True,
        }
        for user_id in user_ids
    }


def serialize_account(user: User, stats: dict[str, Any]) -> dict[str, Any]:
    """6 号 demo 的账号结构；本模块只替换 stats 取值。"""
    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "roles": [{"code": role.code, "name": role.name} for role in user.roles],
        "status": user.status,
        "stats": stats,
        "last_login_at": to_iso(user.last_login_at),
        "created_at": to_iso(user.created_at),
        "updated_at": to_iso(user.updated_at),
        "deleted_at": to_iso(user.deleted_at),
    }
