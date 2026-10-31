"""Token 统计：按日期 + 用户 + Agent + 模型聚合。"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext
from app.core.response import ApiError, ok
from app.models.user import User
from app.models.workspace import AgentRun, CreativeSession, GenerationBatch
from app.modules.admin.service import (
    AGENT_NAMES,
    local_day_end_exclusive,
    local_day_start,
    parse_date_range,
    require_permission,
    today_local,
    validate_keyword,
)

router = APIRouter(prefix="/admin/tokens", tags=["admin-tokens"])

TOKEN_PAGE_SIZE = 20


def _parse_agent_codes(value: str | None) -> list[str] | None:
    """逗号分隔的 Agent code；未知 code 返回 400/10003。"""
    if value is None or value.strip() == "":
        return None
    codes: list[str] = []
    for raw in value.split(","):
        code = raw.strip()
        if code == "":
            continue
        if code not in AGENT_NAMES:
            raise ApiError(400, 10003, "Agent 参数不合法")
        if code not in codes:
            codes.append(code)
    return codes or None


def _counted_condition():
    """计入 Token 的条件：success；failed 且有 Token；skipped 与 0 Token 失败不计。"""
    return or_(
        AgentRun.status == "success",
        and_(
            AgentRun.status == "failed",
            (AgentRun.prompt_tokens + AgentRun.completion_tokens) > 0,
        ),
    )


def _base_query(
    start: date,
    end: date,
    *,
    keyword: str | None,
    agent_codes: list[str] | None,
    model: str | None,
):
    """构造 Token 统计基础查询；用户归属优先会话，其次批次。"""
    owner_user_id = func.coalesce(
        CreativeSession.user_id, GenerationBatch.user_id
    ).label("owner_user_id")
    stat_date = func.date(func.timezone("Asia/Shanghai", AgentRun.created_at)).label(
        "stat_date"
    )

    query = (
        select(
            AgentRun.id.label("run_id"),
            AgentRun.agent_code,
            AgentRun.model_name,
            AgentRun.prompt_tokens,
            AgentRun.completion_tokens,
            owner_user_id,
            User.username,
            User.display_name,
            stat_date,
        )
        .join(CreativeSession, AgentRun.session_id == CreativeSession.id, isouter=True)
        .join(GenerationBatch, AgentRun.batch_id == GenerationBatch.id, isouter=True)
        .join(User, User.id == owner_user_id)
        .where(
            AgentRun.created_at >= local_day_start(start),
            AgentRun.created_at < local_day_end_exclusive(end),
            _counted_condition(),
        )
    )

    if keyword is not None:
        pattern = f"%{keyword}%"
        query = query.where(
            or_(User.username.ilike(pattern), User.display_name.ilike(pattern))
        )
    if agent_codes:
        query = query.where(AgentRun.agent_code.in_(agent_codes))
    if model is not None:
        query = query.where(AgentRun.model_name == model)
    return query


@router.get("/stats")
def token_stats(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    user: str | None = Query(None),
    agent_codes: str | None = Query(None),
    model: str | None = Query(None),
    page: int = Query(1),
    auth: AuthContext = Depends(require_permission("admin.tokens.view")),
    db: Session = Depends(get_db),
) -> dict:
    """Token 统计汇总与明细分页；明细固定每页 20 条。"""
    keyword = validate_keyword(user)
    codes = _parse_agent_codes(agent_codes)
    parsed_start, parsed_end = parse_date_range(start_date, end_date)

    today = today_local()
    start = parsed_start or (today - timedelta(days=6))
    end = parsed_end or today
    if start > end:
        raise ApiError(400, 10003, "参数格式错误")
    model_name = model.strip() if model and model.strip() else None

    base = _base_query(
        start, end, keyword=keyword, agent_codes=codes, model=model_name
    ).subquery()

    prompt_total, completion_total, call_count = db.execute(
        select(
            func.coalesce(func.sum(base.c.prompt_tokens), 0),
            func.coalesce(func.sum(base.c.completion_tokens), 0),
            func.count(base.c.run_id),
        )
    ).one()

    grouped = (
        select(
            base.c.stat_date,
            base.c.owner_user_id,
            base.c.username,
            base.c.display_name,
            base.c.agent_code,
            base.c.model_name,
            func.count(base.c.run_id).label("call_count"),
            func.sum(base.c.prompt_tokens).label("prompt_tokens"),
            func.sum(base.c.completion_tokens).label("completion_tokens"),
        )
        .group_by(
            base.c.stat_date,
            base.c.owner_user_id,
            base.c.username,
            base.c.display_name,
            base.c.agent_code,
            base.c.model_name,
        )
        .subquery()
    )

    total = int(
        db.scalar(select(func.count()).select_from(grouped)) or 0
    )

    page_number = 1 if page < 1 else page
    rows = db.execute(
        select(
            grouped.c.stat_date,
            grouped.c.owner_user_id,
            grouped.c.username,
            grouped.c.display_name,
            grouped.c.agent_code,
            grouped.c.model_name,
            grouped.c.call_count,
            grouped.c.prompt_tokens,
            grouped.c.completion_tokens,
            (grouped.c.prompt_tokens + grouped.c.completion_tokens).label(
                "total_tokens"
            ),
        )
        .order_by(
            grouped.c.stat_date.desc(),
            (grouped.c.prompt_tokens + grouped.c.completion_tokens).desc(),
            grouped.c.owner_user_id.asc(),
            grouped.c.agent_code.asc(),
            grouped.c.model_name.asc(),
        )
        .offset((page_number - 1) * TOKEN_PAGE_SIZE)
        .limit(TOKEN_PAGE_SIZE)
    ).all()

    items = [
        {
            "date": row.stat_date.isoformat(),
            "user_id": int(row.owner_user_id),
            "username": row.username,
            "display_name": row.display_name,
            "agent_code": row.agent_code,
            "agent_name": AGENT_NAMES.get(row.agent_code, row.agent_code),
            "model_name": row.model_name,
            "call_count": int(row.call_count),
            "prompt_tokens": int(row.prompt_tokens),
            "completion_tokens": int(row.completion_tokens),
            "total_tokens": int(row.total_tokens),
        }
        for row in rows
    ]

    print(
        f"[Token统计] 区间 {start}~{end} 汇总调用 {int(call_count)} 次，明细 {len(items)}/{total} 组"
    )
    return ok(
        {
            "summary": {
                "prompt_tokens": int(prompt_total),
                "completion_tokens": int(completion_total),
                "total_tokens": int(prompt_total) + int(completion_total),
                "call_count": int(call_count),
            },
            "items": items,
            "total": total,
            "page": page_number,
            "page_size": TOKEN_PAGE_SIZE,
        }
    )
