"""管理后台聊天记录与 Agent 调用明细（8 号 PRD 最小 demo）。

从原 content/router.py 拆出，避免 7 号内容追溯与 8 号聊天接口互相覆盖。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.config import SystemPrompt
from app.models.user import User
from app.models.workspace import AgentRun, ChatMessage, CreativeSession, GenerationBatch
from app.modules.admin.service import ensure_content_access
from app.modules.workspace.service import to_iso

router = APIRouter(tags=["admin-chat"])


def _is_super(user: User) -> bool:
    return any(role.code == "super_admin" for role in user.roles)


def _check_content_user(auth: AuthContext, db: Session, user_id: int) -> None:
    """管理员不能查看超管账号内容。"""
    ensure_content_access(db, auth, user_id)


# ---- 聊天记录 ----

def _session_summary(db: Session, s: CreativeSession) -> dict:
    user = db.get(User, s.user_id)
    message_count = int(db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.session_id == s.id)) or 0)
    token_row = db.execute(
        select(func.coalesce(func.sum(AgentRun.prompt_tokens), 0), func.coalesce(func.sum(AgentRun.completion_tokens), 0))
        .where(AgentRun.session_id == s.id)
    ).first()
    batch_count = int(db.scalar(select(func.count()).select_from(GenerationBatch).where(GenerationBatch.session_id == s.id)) or 0)
    return {
        "session_id": s.id,
        "user": {"user_id": user.id, "username": user.username, "display_name": user.display_name} if user else None,
        "title": s.title,
        "status": s.status,
        "message_count": message_count,
        "last_message_at": to_iso(s.last_message_at),
        "token_usage": {
            "prompt_tokens": int(token_row[0]) if token_row else 0,
            "completion_tokens": int(token_row[1]) if token_row else 0,
            "total_tokens": int((token_row[0] or 0) + (token_row[1] or 0)) if token_row else 0,
        },
        "batch_count": batch_count,
        "created_at": to_iso(s.created_at),
        "updated_at": to_iso(s.updated_at),
    }


@router.get("/chat/sessions")
def chat_sessions(
    user_keyword: str | None = None,
    title_keyword: str | None = None,
    status: str = "all",
    page: int = Query(1, ge=1),
    page_size: int = Query(20),
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """聊天会话列表。"""
    if status not in ("active", "hidden", "all"):
        raise ApiError(400, 10003, "状态参数不合法")
    if page_size not in (20, 50, 100):
        raise ApiError(400, 10004, "每页条数不合法")

    user_ids = None
    if user_keyword and user_keyword.strip():
        kw = f"%{user_keyword.strip()}%"
        user_ids = set(db.scalars(select(User.id).where(or_(User.username.ilike(kw), User.display_name.ilike(kw)))))

    filters = []
    if not _is_super(auth.user):
        filters.append(~CreativeSession.user_id.in_(select(User.id).where(User.roles.any(code="super_admin"))))
    if user_ids is not None:
        filters.append(CreativeSession.user_id.in_(user_ids))
    if title_keyword and title_keyword.strip():
        filters.append(CreativeSession.title.ilike(f"%{title_keyword.strip()}%"))
    if status in ("active", "hidden"):
        filters.append(CreativeSession.status == status)

    base = select(CreativeSession).where(*filters)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    sessions = list(
        db.scalars(
            base.order_by(func.coalesce(CreativeSession.last_message_at, CreativeSession.created_at).desc(), CreativeSession.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    items = [_session_summary(db, s) for s in sessions]
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/chat/sessions/{session_id}")
def chat_session_detail(
    session_id: int,
    before_id: int | None = None,
    around_id: int | None = None,
    limit: int = Query(20, ge=1, le=50),
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """会话详情与消息窗口。"""
    if before_id is not None and around_id is not None:
        raise ApiError(400, 10001, "参数错误")
    session = db.get(CreativeSession, session_id)
    if session is None:
        raise ApiError(404, 30013, "会话不存在")
    _check_content_user(auth, db, session.user_id)

    msgs = list(db.scalars(select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id.desc())))
    anchor = None
    if around_id is not None:
        anchor = next((m for m in msgs if m.id == around_id), None)
        if anchor is None:
            raise ApiError(404, 30023, "消息不存在")

    if anchor is not None:
        idx = msgs.index(anchor)
        half = (limit - 1) // 2
        window = msgs[max(0, idx - half) : idx + 1 + (limit - 1 - half)]
    elif before_id is not None:
        window = [m for m in msgs if m.id < before_id][:limit]
    else:
        window = msgs[:limit]
    window.reverse()  # 正序

    agent_codes = {m.agent_code for m in window if m.agent_code}
    names = {p.agent_code: p.name for p in db.scalars(select(SystemPrompt).where(SystemPrompt.agent_code.in_(agent_codes)))} if agent_codes else {}

    message_ids = [m.id for m in window]
    runs = list(db.scalars(select(AgentRun).where(AgentRun.message_id.in_(message_ids)).order_by(AgentRun.id.asc()))) if message_ids else []
    runs_by_msg: dict[int, list[AgentRun]] = {}
    batch_ids: set[int] = set()
    for r in runs:
        runs_by_msg.setdefault(r.message_id, []).append(r)
        if r.batch_id:
            batch_ids.add(r.batch_id)
    batches = {b.id: b for b in db.scalars(select(GenerationBatch).where(GenerationBatch.id.in_(batch_ids)))} if batch_ids else {}

    messages = []
    for m in window:
        messages.append(
            {
                "message_id": m.id,
                "role": m.role,
                "agent_code": m.agent_code,
                "agent_name": names.get(m.agent_code) if m.agent_code else None,
                "content": m.content,
                "content_type": m.content_type,
                "token_in": m.token_in,
                "token_out": m.token_out,
                "status": m.status,
                "created_at": to_iso(m.created_at),
                "agent_runs": [
                    {
                        "run_id": r.id,
                        "agent_code": r.agent_code,
                        "agent_name": names.get(r.agent_code, r.agent_code),
                        "status": r.status,
                        "latency_ms": r.latency_ms,
                        "prompt_tokens": r.prompt_tokens,
                        "completion_tokens": r.completion_tokens,
                        "model_name": r.model_name,
                    }
                    for r in runs_by_msg.get(m.id, [])
                ],
                "related_batches": [
                    {
                        "batch_id": b.id,
                        "batch_type": b.batch_type,
                        "status": b.status,
                        "product_name": b.product_name,
                        "created_at": to_iso(b.created_at),
                    }
                    for b in {batches[r.batch_id] for r in runs_by_msg.get(m.id, []) if r.batch_id and r.batch_id in batches}
                ],
            }
        )

    first_id = window[0].id if window else None
    last_id = window[-1].id if window else None
    has_older = bool(first_id and db.scalar(select(ChatMessage.id).where(ChatMessage.session_id == session_id, ChatMessage.id < first_id).limit(1)))
    has_newer = bool(last_id and db.scalar(select(ChatMessage.id).where(ChatMessage.session_id == session_id, ChatMessage.id > last_id).limit(1)))

    return ok(
        {
            "session": _session_summary(db, session),
            "messages": messages,
            "has_older": bool(has_older),
            "has_newer": bool(has_newer),
            "anchor_message_id": anchor.id if anchor else None,
        }
    )


@router.get("/chat/messages/search")
def chat_messages_search(
    q: str = Query(..., min_length=1, max_length=50),
    page: int = Query(1, ge=1),
    page_size: int = Query(20),
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """消息关键词搜索。"""
    kw = f"%{q.strip()}%"
    filters = [ChatMessage.content.ilike(kw)]
    if not _is_super(auth.user):
        filters.append(~ChatMessage.session_id.in_(select(CreativeSession.id).where(CreativeSession.user_id.in_(select(User.id).where(User.roles.any(code="super_admin"))))))

    base = select(ChatMessage).where(*filters)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    msgs = list(db.scalars(base.order_by(ChatMessage.id.desc()).offset((page - 1) * page_size).limit(page_size)))
    items = []
    for m in msgs:
        session = db.get(CreativeSession, m.session_id)
        user = db.get(User, session.user_id) if session else None
        items.append(
            {
                "message_id": m.id,
                "session_id": m.session_id,
                "session_title": session.title if session else None,
                "user_id": user.id if user else None,
                "username": user.username if user else None,
                "display_name": user.display_name if user else None,
                "role": m.role,
                "content": m.content,
                "created_at": to_iso(m.created_at),
            }
        )
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/agent-runs/{run_id}")
def agent_run_detail(
    run_id: int,
    full: bool = False,
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """Agent 调用明细。"""
    run = db.get(AgentRun, run_id)
    if run is None:
        raise ApiError(404, 30024, "调用记录不存在")
    if run.session_id:
        session = db.get(CreativeSession, run.session_id)
        if session:
            _check_content_user(auth, db, session.user_id)

    show_full = full and _is_super(auth.user)
    if full and not _is_super(auth.user):
        raise ApiError(403, 20005, "无权限")

    return ok(
        {
            "run_id": run.id,
            "session_id": run.session_id,
            "message_id": run.message_id,
            "batch_id": run.batch_id,
            "agent_code": run.agent_code,
            "status": run.status,
            "model_name": run.model_name,
            "input_summary": run.input_summary,
            "output_summary": run.output_summary,
            "input_full": run.input_full if show_full else None,
            "output_full": run.output_full if show_full else None,
            "prompt_tokens": run.prompt_tokens,
            "completion_tokens": run.completion_tokens,
            "latency_ms": run.latency_ms,
            "error_message": run.error_message,
            "created_at": to_iso(run.created_at),
        }
    )
