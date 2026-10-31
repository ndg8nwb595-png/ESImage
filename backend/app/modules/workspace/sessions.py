"""会话列表、消息分页与聊天轻链路（SSE）。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import AuthContext
from app.core.response import ApiError, ok
from app.models.workspace import AgentRun, ChatMessage, CreativeSession, GenerationBatch
from app.modules.workspace.schemas import ChatMessageRequest
from app.modules.workspace.service import (
    get_owned_session,
    merge_requirement_summary,
    require_permission,
    session_title_from_message,
    to_iso,
    validate_idempotency_key,
    validate_message_content,
    validate_product_name,
    validate_size,
    validate_style_text,
    validate_template_id,
    workspace_lock,
)

router = APIRouter(tags=["workspace"])

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _session_item(db: Session, session: CreativeSession) -> dict[str, Any]:
    """组装会话列表项；补充 demo 约定的摘要与最近批次。"""
    preview = db.scalar(
        select(ChatMessage.content)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
    )
    latest_batch_id = db.scalar(
        select(GenerationBatch.id)
        .where(GenerationBatch.session_id == session.id)
        .order_by(GenerationBatch.created_at.desc(), GenerationBatch.id.desc())
        .limit(1)
    )
    return {
        "session_id": session.id,
        "title": session.title,
        "status": session.status,
        "last_message_at": to_iso(session.last_message_at),
        "last_message_preview": preview[:30] if preview else None,
        "latest_batch_id": latest_batch_id,
        "created_at": to_iso(session.created_at),
        "updated_at": to_iso(session.updated_at),
    }


@router.get("/sessions")
def list_sessions(
    auth: AuthContext = Depends(require_permission("user.workspace")),
    db: Session = Depends(get_db),
) -> dict:
    """当前用户活跃会话列表，最多 50 条。"""
    sessions = list(
        db.scalars(
            select(CreativeSession)
            .where(
                CreativeSession.user_id == auth.user.id,
                CreativeSession.status == "active",
            )
            .order_by(
                CreativeSession.last_message_at.desc().nulls_last(),
                CreativeSession.created_at.desc(),
            )
            .limit(50)
        )
    )
    items = [_session_item(db, session) for session in sessions]
    return ok({"items": items, "total": len(items)})


@router.get("/sessions/{session_id}/messages")
def list_messages(
    session_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("user.workspace")),
    db: Session = Depends(get_db),
) -> dict:
    """消息分页：page=1 为最新一页，页内按时间升序返回。"""
    session = get_owned_session(db, auth.user.id, session_id)

    total = int(
        db.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.session_id == session.id)
        )
        or 0
    )
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    rows.reverse()

    items = [
        {
            "message_id": message.id,
            "session_id": message.session_id,
            "role": message.role,
            "agent_code": message.agent_code,
            "content": message.content,
            "content_type": message.content_type,
            "status": message.status,
            "token_in": message.token_in,
            "token_out": message.token_out,
            "created_at": to_iso(message.created_at),
        }
        for message in rows
    ]
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


def _build_reply(product_name: str, style_text: str | None) -> str:
    """未配置文本模型时的固定演示回复。"""
    if style_text:
        return f"已了解商品「{product_name}」，风格按「{style_text}」处理。可以继续补充卖点、目标人群或使用场景。"
    return (
        f"已了解商品「{product_name}」。建议风格：简洁白底、高级质感、生活场景、国潮。"
        "你可以用自然语言选择或自行补充。"
    )


def _find_duplicate(
    db: Session,
    user_id: int,
    session_id: int | None,
    client_message_id: str,
) -> tuple[ChatMessage | None, CreativeSession | None]:
    """按会话或用户维度查找已保存的用户消息。"""
    if session_id is not None:
        message = db.scalar(
            select(ChatMessage).where(
                ChatMessage.session_id == session_id,
                ChatMessage.client_message_id == client_message_id,
            )
        )
        return message, None

    row = db.execute(
        select(ChatMessage, CreativeSession)
        .join(CreativeSession, ChatMessage.session_id == CreativeSession.id)
        .where(
            CreativeSession.user_id == user_id,
            ChatMessage.client_message_id == client_message_id,
        )
        .order_by(ChatMessage.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None
    return row[0], row[1]


def _assistant_after(db: Session, session_id: int, user_message_id: int) -> ChatMessage | None:
    """取该用户消息之后最新的一条 Agent 回复（重试可能产生多条）。"""
    return db.scalar(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "assistant",
            ChatMessage.id > user_message_id,
        )
        .order_by(ChatMessage.id.desc())
        .limit(1)
    )


def _stream_reply(
    *,
    session_id: int,
    assistant_id: int,
    reply_text: str,
    product_name: str,
    user_content: str,
) -> Iterator[str]:
    """输出 SSE 事件，并在结束时落库；断线时把未完成消息标记为 failed。"""
    completed = False
    try:
        print(f"[SSE] 开始回复 session_id={session_id} message_id={assistant_id}")
        yield _sse("meta", {"message_id": assistant_id, "session_id": session_id})
        yield _sse("agent_status", {"agent_code": "planner", "status": "started"})
        yield _sse("agent_status", {"agent_code": "planner", "status": "finished"})
        yield _sse("agent_status", {"agent_code": "product_understanding", "status": "started"})

        # 按固定长度切片模拟流式输出
        for start in range(0, len(reply_text), 12):
            yield _sse("delta", {"content": reply_text[start : start + 12]})

        yield _sse("agent_status", {"agent_code": "product_understanding", "status": "finished"})

        # 流结束后写库：回复内容、需求摘要、Agent 调用明细
        with SessionLocal() as write_db:
            assistant = write_db.get(ChatMessage, assistant_id)
            chat_session = write_db.get(CreativeSession, session_id)
            if assistant is not None and assistant.status == "sending":
                assistant.content = reply_text
                assistant.status = "done"
            summary: dict[str, Any] = {}
            if chat_session is not None:
                summary = merge_requirement_summary(chat_session.requirement_summary, product_name)
                chat_session.requirement_summary = summary
                chat_session.last_message_at = datetime.now(timezone.utc)
            for agent_code in ("planner", "product_understanding"):
                write_db.add(
                    AgentRun(
                        session_id=session_id,
                        message_id=assistant_id,
                        agent_code=agent_code,
                        status="success",
                        model_name=None,
                        input_summary=user_content[:200],
                        output_summary=reply_text[:200],
                        prompt_tokens=0,
                        completion_tokens=0,
                        latency_ms=0,
                    )
                )
            write_db.commit()
        completed = True

        yield _sse(
            "done",
            {
                "message_id": assistant_id,
                "token_in": 0,
                "token_out": 0,
                "requirement_summary": summary,
            },
        )
        print(f"[SSE] 回复完成 session_id={session_id} message_id={assistant_id}")
    finally:
        if not completed:
            # 客户端断线或写库失败：把仍处于 sending 的回复标记为失败，允许同幂等键重发
            try:
                with SessionLocal() as write_db:
                    assistant = write_db.get(ChatMessage, assistant_id)
                    if assistant is not None and assistant.status == "sending":
                        assistant.status = "failed"
                        write_db.commit()
                        print(f"[SSE] 连接中断，消息标记失败 message_id={assistant_id}")
            except Exception:
                pass


def _replay_stream(db: Session, session: CreativeSession, assistant: ChatMessage) -> StreamingResponse:
    """已完成消息的重放：meta + 一次完整 delta + done。"""
    summary = session.requirement_summary or {}

    def generator() -> Iterator[str]:
        print(f"[SSE] 重放消息 session_id={session.id} message_id={assistant.id}")
        yield _sse("meta", {"message_id": assistant.id, "session_id": session.id})
        yield _sse("delta", {"content": assistant.content})
        yield _sse(
            "done",
            {
                "message_id": assistant.id,
                "token_in": assistant.token_in,
                "token_out": assistant.token_out,
                "requirement_summary": summary,
            },
        )

    return StreamingResponse(generator(), media_type="text/event-stream", headers=SSE_HEADERS)


def _duplicate_response(
    db: Session,
    session: CreativeSession,
    user_message: ChatMessage,
    *,
    product_name: str,
    style_text: str | None,
    user_content: str,
) -> StreamingResponse:
    """处理重复幂等键：已完成重放、处理中 409、失败则重新生成回复。"""
    assistant = _assistant_after(db, session.id, user_message.id)
    if assistant is None or assistant.status == "sending":
        raise ApiError(409, 30005, "消息正在处理中，请稍候")

    if assistant.status == "done":
        return _replay_stream(db, session, assistant)

    # 上次回复失败：复用原用户消息，新建一条 Agent 回复，不产生重复用户消息
    reply_text = _build_reply(product_name, style_text)
    retry_assistant = ChatMessage(
        session_id=session.id,
        role="assistant",
        agent_code="product_understanding",
        content="",
        content_type="text",
        status="sending",
    )
    db.add(retry_assistant)
    session.last_message_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(retry_assistant)
    return StreamingResponse(
        _stream_reply(
            session_id=session.id,
            assistant_id=retry_assistant.id,
            reply_text=reply_text,
            product_name=product_name,
            user_content=user_content,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _handle_chat(
    payload: ChatMessageRequest,
    path_session_id: int | None,
    auth: AuthContext,
    db: Session,
) -> StreamingResponse:
    client_message_id = validate_idempotency_key(payload.client_message_id, "client_message_id")
    content = validate_message_content(payload.content)
    product_name = validate_product_name(payload.params.product_name)
    style_text = validate_style_text(payload.params.style_text)
    validate_template_id(payload.params.template_id)
    validate_size(payload.params.width, payload.params.height)

    requested_session_id = path_session_id if path_session_id is not None else payload.session_id
    reply_text = _build_reply(product_name, style_text)

    # 进程内锁 + 数据库事务：避免首条消息并发创建两个会话，或并发插入重复消息
    with workspace_lock():
        session: CreativeSession | None = None
        if requested_session_id is not None:
            session = get_owned_session(db, auth.user.id, requested_session_id)
            duplicate, _ = _find_duplicate(db, auth.user.id, session.id, client_message_id)
            if duplicate is not None:
                return _duplicate_response(
                    db,
                    session,
                    duplicate,
                    product_name=product_name,
                    style_text=style_text,
                    user_content=content,
                )
        else:
            duplicate, existing_session = _find_duplicate(
                db, auth.user.id, None, client_message_id
            )
            if duplicate is not None and existing_session is not None:
                return _duplicate_response(
                    db,
                    existing_session,
                    duplicate,
                    product_name=product_name,
                    style_text=style_text,
                    user_content=content,
                )
            session = CreativeSession(
                user_id=auth.user.id,
                title=session_title_from_message(content),
                status="active",
                last_message_at=datetime.now(timezone.utc),
            )
            db.add(session)
            db.flush()

        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            agent_code=None,
            content=content,
            content_type="text",
            client_message_id=client_message_id,
            status="done",
        )
        db.add(user_message)
        session.last_message_at = datetime.now(timezone.utc)

        assistant_message = ChatMessage(
            session_id=session.id,
            role="assistant",
            agent_code="product_understanding",
            content="",
            content_type="text",
            status="sending",
        )
        db.add(assistant_message)
        try:
            db.commit()
        except IntegrityError:
            # 并发请求抢到同一幂等键：回滚后按已保存消息处理
            db.rollback()
            duplicate, existing_session = _find_duplicate(
                db, auth.user.id, requested_session_id, client_message_id
            )
            if duplicate is not None and existing_session is not None:
                return _duplicate_response(
                    db,
                    existing_session,
                    duplicate,
                    product_name=product_name,
                    style_text=style_text,
                    user_content=content,
                )
            if duplicate is not None and requested_session_id is not None:
                session = get_owned_session(db, auth.user.id, requested_session_id)
                return _duplicate_response(
                    db,
                    session,
                    duplicate,
                    product_name=product_name,
                    style_text=style_text,
                    user_content=content,
                )
            raise
        db.refresh(assistant_message)
        session_id = session.id
        assistant_id = assistant_message.id

    return StreamingResponse(
        _stream_reply(
            session_id=session_id,
            assistant_id=assistant_id,
            reply_text=reply_text,
            product_name=product_name,
            user_content=content,
        ),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.post("/sessions/messages")
def send_first_message(
    payload: ChatMessageRequest,
    auth: AuthContext = Depends(require_permission("user.workspace")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """首条消息：可无会话，后端在同一事务内创建。"""
    return _handle_chat(payload, None, auth, db)


@router.post("/sessions/{session_id}/messages")
def send_session_message(
    session_id: int,
    payload: ChatMessageRequest,
    auth: AuthContext = Depends(require_permission("user.workspace")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """已有会话发消息；路径中的会话必须属于当前用户。"""
    return _handle_chat(payload, session_id, auth, db)
