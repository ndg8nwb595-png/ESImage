"""概览四卡与 Token 统计（7 号 PRD 最小 demo）。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.config import SystemPrompt
from app.models.user import User
from app.models.workspace import AgentRun, CreativeSession, GeneratedImage, GenerationBatch

router = APIRouter(tags=["admin-dashboard"])

KNOWN_AGENTS = {
    "planner",
    "product_understanding",
    "copywriter",
    "prompt_builder",
    "image_generator",
    "quality_reviewer",
    "repairer",
    "platform_rule",
}


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ApiError(400, 10003, "参数格式错误") from None


def _day_range_utc(day: date) -> tuple[datetime, datetime]:
    """某天（Asia/Shanghai）对应的 UTC 起止区间。"""
    start = datetime.combine(day, time.min, tzinfo=settings.TZ)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


@router.get("/dashboard/summary")
def dashboard_summary(
    auth: AuthContext = Depends(require_permission("admin.dashboard.view")),
    db: Session = Depends(get_db),
) -> dict:
    """概览四张统计卡片。"""
    today = datetime.now(settings.TZ).date()
    start_utc, end_utc = _day_range_utc(today)

    user_total = int(
        db.scalar(select(func.count()).select_from(User).where(User.status != "deleted")) or 0
    )
    image_filter = (
        GeneratedImage.image_type == "final",
        GeneratedImage.status == "success",
    )
    today_image_count = int(
        db.scalar(
            select(func.count())
            .select_from(GeneratedImage)
            .where(*image_filter, GeneratedImage.created_at >= start_utc, GeneratedImage.created_at < end_utc)
        )
        or 0
    )
    total_image_count = int(
        db.scalar(select(func.count()).select_from(GeneratedImage).where(*image_filter)) or 0
    )
    today_token_total = int(
        db.scalar(
            select(func.coalesce(func.sum(AgentRun.prompt_tokens + AgentRun.completion_tokens), 0))
            .select_from(AgentRun)
            .where(
                AgentRun.created_at >= start_utc,
                AgentRun.created_at < end_utc,
                or_(
                    AgentRun.status == "success",
                    (AgentRun.status == "failed")
                    & ((AgentRun.prompt_tokens + AgentRun.completion_tokens) > 0),
                ),
            )
        )
        or 0
    )

    return ok(
        {
            "user_total": user_total,
            "today_image_count": today_image_count,
            "total_image_count": total_image_count,
            "today_token_total": today_token_total,
        }
    )


@router.get("/tokens/stats")
def token_stats(
    start_date: str | None = None,
    end_date: str | None = None,
    user: str | None = None,
    agent_codes: str | None = None,
    model: str | None = None,
    page: int = Query(1, ge=1),
    auth: AuthContext = Depends(require_permission("admin.tokens.view")),
    db: Session = Depends(get_db),
) -> dict:
    """Token 统计：按 (日期, 用户, Agent, 模型) 聚合。"""
    today = datetime.now(settings.TZ).date()
    start = _parse_date(start_date) or (today - timedelta(days=6))
    end = _parse_date(end_date) or today
    if start > end:
        raise ApiError(400, 10003, "参数格式错误")

    codes = [c.strip() for c in (agent_codes or "").split(",") if c.strip()]
    if codes and any(c not in KNOWN_AGENTS for c in codes):
        raise ApiError(400, 10003, "Agent 参数不合法")

    start_utc, _ = _day_range_utc(start)
    _, end_utc = _day_range_utc(end)

    filters = [
        AgentRun.created_at >= start_utc,
        AgentRun.created_at < end_utc,
        or_(
            AgentRun.status == "success",
            (AgentRun.status == "failed")
            & ((AgentRun.prompt_tokens + AgentRun.completion_tokens) > 0),
        ),
    ]
    if codes:
        filters.append(AgentRun.agent_code.in_(codes))
    if model and model.strip():
        filters.append(AgentRun.model_name == model.strip())

    attributed_user_id = func.coalesce(CreativeSession.user_id, GenerationBatch.user_id)
    stmt = (
        select(
            AgentRun.created_at,
            AgentRun.agent_code,
            AgentRun.model_name,
            AgentRun.prompt_tokens,
            AgentRun.completion_tokens,
            attributed_user_id.label("user_id"),
            SystemPrompt.name.label("agent_name"),
        )
        .outerjoin(CreativeSession, AgentRun.session_id == CreativeSession.id)
        .outerjoin(GenerationBatch, AgentRun.batch_id == GenerationBatch.id)
        .outerjoin(SystemPrompt, SystemPrompt.agent_code == AgentRun.agent_code)
        .where(*filters)
    )
    rows = db.execute(stmt).all()

    # 用户关键词过滤：先按用户名/显示名查 id 集合，再过滤
    user_ids: set[int] | None = None
    if user and user.strip():
        kw = f"%{user.strip()}%"
        user_ids = set(
            db.scalars(
                select(User.id).where(
                    or_(User.username.ilike(kw), User.display_name.ilike(kw))
                )
            )
        )

    # 用户 id -> (username, display_name)
    needed_ids = {r.user_id for r in rows if r.user_id is not None}
    users_map: dict[int, User] = {}
    if needed_ids:
        users_map = {u.id: u for u in db.scalars(select(User).where(User.id.in_(needed_ids)))}

    groups: dict[tuple, dict] = {}
    for row in rows:
        uid = row.user_id
        if user_ids is not None and (uid is None or uid not in user_ids):
            continue
        day = row.created_at.astimezone(settings.TZ).strftime("%Y-%m-%d")
        key = (day, uid, row.agent_code, row.model_name)
        group = groups.setdefault(
            key,
            {
                "date": day,
                "user_id": uid,
                "username": users_map[uid].username if uid in users_map else None,
                "display_name": users_map[uid].display_name if uid in users_map else None,
                "agent_code": row.agent_code,
                "agent_name": row.agent_name or row.agent_code,
                "model_name": row.model_name,
                "call_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        )
        group["call_count"] += 1
        group["prompt_tokens"] += row.prompt_tokens
        group["completion_tokens"] += row.completion_tokens
        group["total_tokens"] += row.prompt_tokens + row.completion_tokens

    items = sorted(
        groups.values(),
        key=lambda g: (
            g["date"],
            -(g["total_tokens"]),
            g["user_id"] or 0,
            g["agent_code"],
            g["model_name"] or "",
        ),
        reverse=True,
    )

    summary = {
        "prompt_tokens": sum(g["prompt_tokens"] for g in items),
        "completion_tokens": sum(g["completion_tokens"] for g in items),
        "total_tokens": sum(g["total_tokens"] for g in items),
        "call_count": sum(g["call_count"] for g in items),
    }
    total = len(items)
    page_size = 20
    start_idx = (page - 1) * page_size
    paged = items[start_idx : start_idx + page_size]

    return ok(
        {
            "summary": summary,
            "items": paged,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )
