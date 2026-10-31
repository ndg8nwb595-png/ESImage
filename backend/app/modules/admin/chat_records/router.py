"""8 号管理后台-聊天记录：HTTP 接口。

覆盖接口文档 §3~§5：
- 聊天会话列表
- 会话详情与消息窗口
- 消息关键词搜索
- Agent 调用明细
聊天记录只读，不提供发送、编辑、删除、导出与恢复会话。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.user import User
from app.models.workspace import (
    AgentRun,
    ChatMessage,
    CreativeSession,
    GenerationBatch,
)
from app.modules.admin.chat_records.service import (
    agent_names,
    build_snippet,
    escape_like,
    get_visible_session,
    is_super,
    normalize_keyword,
    parse_day_range,
    session_summaries,
    session_summary,
    super_admin_user_ids,
    visible_session_ids,
)
from app.modules.chat.service import expire_stale_messages
from app.modules.workspace.service import to_iso

router = APIRouter(tags=["admin-chat-records"])

SESSION_PAGE_SIZES = (20, 50, 100)
SESSION_STATUSES = ("active", "hidden", "all")
SEARCH_PAGE_SIZE = 20


@router.get("/chat/sessions")
def list_chat_sessions(
    user_keyword: str | None = None,
    title_keyword: str | None = None,
    last_message_from: str | None = None,
    last_message_to: str | None = None,
    status: str = "all",
    page: int = 1,
    page_size: int = 20,
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """聊天会话列表：筛选、分页与可见范围过滤。"""
    # 接口文档 §3.1：空字符串参数按未提供处理
    status = (status or "").strip() or "all"
    if status not in SESSION_STATUSES:
        raise ApiError(400, 10003, "状态参数不合法")
    if page_size not in SESSION_PAGE_SIZES:
        raise ApiError(400, 10004, "每页条数仅支持 20/50/100")
    if page < 1:
        page = 1

    user_keyword_value = normalize_keyword(user_keyword)
    title_keyword_value = normalize_keyword(title_keyword)

    from_range = parse_day_range(last_message_from, field="最后消息起始日期")
    to_range = parse_day_range(last_message_to, field="最后消息结束日期")
    if from_range and to_range and from_range[0] > to_range[0]:
        raise ApiError(400, 10004, "日期范围不合法")

    filters = []
    if not is_super(auth.user):
        filters.append(~CreativeSession.user_id.in_(super_admin_user_ids()))

    if user_keyword_value:
        pattern = f"%{escape_like(user_keyword_value)}%"
        matching_user_ids = select(User.id).where(
            or_(
                User.username.ilike(pattern, escape="\\"),
                User.display_name.ilike(pattern, escape="\\"),
            )
        )
        filters.append(CreativeSession.user_id.in_(matching_user_ids))

    if title_keyword_value:
        filters.append(
            CreativeSession.title.ilike(
                f"%{escape_like(title_keyword_value)}%", escape="\\"
            )
        )
    if from_range:
        filters.append(CreativeSession.last_message_at >= from_range[0])
    if to_range:
        filters.append(CreativeSession.last_message_at <= to_range[1])
    if status in ("active", "hidden"):
        filters.append(CreativeSession.status == status)

    base = select(CreativeSession).where(*filters)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    sessions = list(
        db.scalars(
            base.order_by(
                func.coalesce(
                    CreativeSession.last_message_at, CreativeSession.created_at
                ).desc(),
                CreativeSession.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return ok(
        {
            "items": session_summaries(db, sessions),
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


def _message_window(
    db: Session,
    session_id: int,
    *,
    before_id: int | None,
    around_id: int | None,
    limit: int,
) -> tuple[list[ChatMessage], ChatMessage | None]:
    """按接口文档 §4.2 取消息窗口；异常在调用方校验。"""
    if around_id is not None:
        anchor = db.scalar(
            select(ChatMessage).where(
                ChatMessage.id == around_id,
                ChatMessage.session_id == session_id,
            )
        )
        if anchor is None:
            raise ApiError(404, 30023, "消息不存在")
        older_count = (limit - 1) // 2
        older = list(
            db.scalars(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.id < anchor.id,
                )
                .order_by(ChatMessage.id.desc())
                .limit(older_count)
            )
        )
        older.reverse()
        # 接口文档 §4.2：按“实际已取更早条数”补齐更新消息，总数不超过 limit
        newer_count = limit - 1 - len(older)
        newer = list(
            db.scalars(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.id > anchor.id,
                )
                .order_by(ChatMessage.id.asc())
                .limit(newer_count)
            )
        )
        return older + [anchor] + newer, anchor

    statement = select(ChatMessage).where(ChatMessage.session_id == session_id)
    if before_id is not None:
        statement = statement.where(ChatMessage.id < before_id)
    rows = list(
        db.scalars(statement.order_by(ChatMessage.id.desc()).limit(limit))
    )
    rows.reverse()
    return rows, None


@router.get("/chat/sessions/{session_id}")
def get_chat_session_detail(
    session_id: int,
    before_id: int | None = None,
    around_id: int | None = None,
    limit: int = 20,
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """会话详情与消息窗口。"""
    if before_id is not None and before_id <= 0:
        raise ApiError(400, 10003, "before_id 需为正整数")
    if around_id is not None and around_id <= 0:
        raise ApiError(400, 10003, "around_id 需为正整数")
    if limit < 1 or limit > 50:
        raise ApiError(400, 10004, "limit 需在 1~50 之间")
    if before_id is not None and around_id is not None:
        raise ApiError(400, 10001, "参数错误")

    session = get_visible_session(db, auth, session_id)

    # 接口文档 §4.5：超过阈值的 sending Agent 消息惰性标记为 failed
    expire_stale_messages(db, session_id)

    messages, anchor = _message_window(
        db,
        session_id,
        before_id=before_id,
        around_id=around_id,
        limit=limit,
    )

    message_ids = [message.id for message in messages]
    runs = (
        list(
            db.scalars(
                select(AgentRun)
                .where(AgentRun.message_id.in_(message_ids))
                .order_by(AgentRun.id.asc())
            )
        )
        if message_ids
        else []
    )
    runs_by_message: dict[int, list[AgentRun]] = {}
    batch_ids: set[int] = set()
    for run in runs:
        if run.message_id is not None:
            runs_by_message.setdefault(run.message_id, []).append(run)
        if run.batch_id is not None:
            batch_ids.add(run.batch_id)

    batches = (
        {
            batch.id: batch
            for batch in db.scalars(
                select(GenerationBatch).where(GenerationBatch.id.in_(batch_ids))
            )
        }
        if batch_ids
        else {}
    )

    all_agent_codes = {message.agent_code for message in messages if message.agent_code}
    all_agent_codes |= {run.agent_code for run in runs}
    names = agent_names(db, all_agent_codes)

    message_items = []
    for message in messages:
        related_batch_ids = list(
            dict.fromkeys(
                run.batch_id
                for run in runs_by_message.get(message.id, [])
                if run.batch_id is not None
            )
        )
        message_items.append(
            {
                "message_id": message.id,
                "role": message.role,
                "agent_code": message.agent_code,
                "agent_name": (
                    names.get(message.agent_code) if message.agent_code else None
                ),
                "content": message.content,
                "content_type": message.content_type,
                "token_in": message.token_in,
                "token_out": message.token_out,
                "status": message.status,
                "created_at": to_iso(message.created_at),
                "agent_runs": [
                    {
                        "run_id": run.id,
                        "agent_code": run.agent_code,
                        "agent_name": names.get(run.agent_code, run.agent_code),
                        "status": run.status,
                        "latency_ms": run.latency_ms,
                        "prompt_tokens": run.prompt_tokens,
                        "completion_tokens": run.completion_tokens,
                        "model_name": run.model_name,
                    }
                    for run in runs_by_message.get(message.id, [])
                ],
                "related_batches": [
                    {
                        "batch_id": batches[batch_id].id,
                        "batch_type": batches[batch_id].batch_type,
                        "status": batches[batch_id].status,
                        "product_name": batches[batch_id].product_name,
                        "created_at": to_iso(batches[batch_id].created_at),
                    }
                    for batch_id in related_batch_ids
                    if batch_id in batches
                ],
            }
        )

    first_id = messages[0].id if messages else None
    last_id = messages[-1].id if messages else None
    has_older = bool(
        first_id is not None
        and db.scalar(
            select(ChatMessage.id)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.id < first_id,
            )
            .limit(1)
        )
    )
    has_newer = bool(
        last_id is not None
        and db.scalar(
            select(ChatMessage.id)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.id > last_id,
            )
            .limit(1)
        )
    )

    return ok(
        {
            "session": session_summary(db, session),
            "messages": message_items,
            "has_older": has_older,
            "has_newer": has_newer,
            "anchor_message_id": anchor.id if anchor is not None else None,
        }
    )


@router.get("/chat/messages/search")
def search_chat_messages(
    keyword: str | None = None,
    page: int = 1,
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """消息关键词搜索：大小写不敏感子串匹配，固定每页 20 条。"""
    keyword_value = (keyword or "").strip()
    if not keyword_value:
        raise ApiError(400, 10002, "请输入搜索关键词")
    if len(keyword_value) > 100:
        raise ApiError(400, 10004, "关键词不能超过 100 个字符")
    if page < 1:
        raise ApiError(400, 10003, "页码需为正整数")

    filters = [
        ChatMessage.content.ilike(
            f"%{escape_like(keyword_value)}%", escape="\\"
        )
    ]
    session_scope = visible_session_ids(auth)
    if session_scope is not None:
        filters.append(ChatMessage.session_id.in_(session_scope))

    base = select(ChatMessage).where(*filters)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    messages = list(
        db.scalars(
            base.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .offset((page - 1) * SEARCH_PAGE_SIZE)
            .limit(SEARCH_PAGE_SIZE)
        )
    )

    # 批量读取会话、用户与 Agent 名称，避免逐条查询
    session_ids = {message.session_id for message in messages}
    sessions = (
        {
            session.id: session
            for session in db.scalars(
                select(CreativeSession).where(CreativeSession.id.in_(session_ids))
            )
        }
        if session_ids
        else {}
    )
    user_ids = {session.user_id for session in sessions.values()}
    users = (
        {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids)))}
        if user_ids
        else {}
    )
    names = agent_names(
        db, {message.agent_code for message in messages if message.agent_code}
    )

    items = []
    for message in messages:
        session = sessions.get(message.session_id)
        user = users.get(session.user_id) if session is not None else None
        items.append(
            {
                "message_id": message.id,
                "session_id": message.session_id,
                "session_title": session.title if session is not None else None,
                "session_status": session.status if session is not None else None,
                "user": (
                    {
                        "user_id": user.id,
                        "username": user.username,
                        "display_name": user.display_name,
                    }
                    if user is not None
                    else None
                ),
                "role": message.role,
                "agent_code": message.agent_code,
                "agent_name": (
                    names.get(message.agent_code) if message.agent_code else None
                ),
                "snippet": build_snippet(message.content, keyword_value),
                "created_at": to_iso(message.created_at),
            }
        )

    return ok(
        {
            "items": items,
            "total": total,
            "page": page,
            "page_size": SEARCH_PAGE_SIZE,
        }
    )


@router.get("/agent-runs/{run_id}")
def get_agent_run_detail(
    run_id: int,
    full: bool = False,
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """Agent 调用明细；完整输入/输出仅超管可看。"""
    run = db.get(AgentRun, run_id)
    if run is None:
        raise ApiError(404, 30020, "调用记录不存在")

    # 通过会话或批次推导归属用户
    owner_id: int | None = None
    if run.session_id is not None:
        session = db.get(CreativeSession, run.session_id)
        if session is not None:
            owner_id = session.user_id
    if owner_id is None and run.batch_id is not None:
        batch = db.get(GenerationBatch, run.batch_id)
        if batch is not None:
            # 接口文档 §5.3：batch_id -> generation_batches.session_id 推导归属
            batch_session = db.get(CreativeSession, batch.session_id)
            owner_id = (
                batch_session.user_id
                if batch_session is not None
                else batch.user_id
            )

    is_super_user = is_super(auth.user)
    if not is_super_user:
        if full:
            raise ApiError(403, 20005, "无权限")
        if owner_id is None:
            raise ApiError(403, 20005, "无权限")
        owner = db.get(User, owner_id)
        if owner is not None and is_super(owner):
            raise ApiError(403, 20005, "无权限")

    show_full = full and is_super_user
    name = agent_names(db, {run.agent_code}).get(run.agent_code, run.agent_code)
    prompt_tokens = int(run.prompt_tokens or 0)
    completion_tokens = int(run.completion_tokens or 0)

    return ok(
        {
            "run_id": run.id,
            "session_id": run.session_id,
            "message_id": run.message_id,
            "batch_id": run.batch_id,
            "image_id": run.image_id,
            "agent_code": run.agent_code,
            "agent_name": name,
            "status": run.status,
            "model_name": run.model_name,
            "created_at": to_iso(run.created_at),
            "latency_ms": run.latency_ms,
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "input_summary": run.input_summary,
            "output_summary": run.output_summary,
            "input_full": run.input_full if show_full else None,
            "output_full": run.output_full if show_full else None,
            "full_available": is_super_user,
            "error_message": run.error_message,
        }
    )
