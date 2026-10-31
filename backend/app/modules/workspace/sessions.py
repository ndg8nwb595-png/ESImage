"""会话列表、消息分页与聊天轻链路（SSE）。

3 号增量：meta.duplicate、done.requirement_changed、10 轮上下文、
惰性超时、上传图参数校验与 agent_runs 明细；基础契约沿用 2 号 demo。
"""

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

from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.deps import AuthContext
from app.core.response import ApiError, ok
from app.models.workspace import AgentRun, ChatMessage, CreativeSession, GenerationBatch
from app.modules.chat.agents import (
    ChatParams,
    build_context,
    context_as_text,
    merge_agent_summary,
)
from app.modules.chat.model import (
    ModelCallError,
    PlannerOutput,
    ProductStream,
    real_model_enabled,
    run_planner,
    stream_product,
)
from app.modules.chat.service import (
    compute_requirement_changed,
    expire_stale_messages,
    validate_upload_ids,
)
from app.modules.chat.stream import sse as _sse
from app.modules.chat.stream import with_heartbeat
from app.modules.workspace.schemas import ChatMessageRequest
from app.modules.workspace.service import (
    get_owned_session,
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
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _streaming_response(events: Iterator[str]) -> StreamingResponse:
    """统一 SSE 响应：按配置间隔插入 ping，客户端断开时关闭内层生成器。"""
    return StreamingResponse(
        with_heartbeat(events, settings.SSE_HEARTBEAT_SECONDS),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


def _session_item(db: Session, session: CreativeSession) -> dict[str, Any]:
    """组装会话列表项；补充 demo 约定的摘要与最近批次。"""
    raw_preview = db.scalar(
        select(ChatMessage.content)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(1)
    )
    # 3 号补充约定：去除换行与首尾空格后截取前 30 个字符
    preview_text = (
        raw_preview.replace("\r", "").replace("\n", "").strip() if raw_preview else ""
    )
    preview = preview_text[:30] if preview_text else None
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
        "last_message_preview": preview,
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

    # 3 号增量：查询时惰性把超过阈值的 sending Agent 消息标记为 failed
    expire_stale_messages(db, session.id)

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
            # 已隐藏会话不可再通过首条消息接口重放或写回
            CreativeSession.status == "active",
            ChatMessage.client_message_id == client_message_id,
        )
        .order_by(ChatMessage.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return None, None
    return row[0], row[1]


def _assistant_for_user_message(
    db: Session, session_id: int, user_message_id: int
) -> ChatMessage | None:
    """取该用户消息对应的 Agent 回复。

    聊天消息表没有“回复了哪条用户消息”的外键，因此按 id 区间定位：
    只取该用户消息之后、下一条用户消息之前的最新一条 Agent 回复。
    """
    next_user_id = db.scalar(
        select(func.min(ChatMessage.id)).where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "user",
            ChatMessage.id > user_message_id,
        )
    )
    statement = select(ChatMessage).where(
        ChatMessage.session_id == session_id,
        ChatMessage.role == "assistant",
        ChatMessage.id > user_message_id,
    )
    if next_user_id is not None:
        statement = statement.where(ChatMessage.id < next_user_id)
    return db.scalar(statement.order_by(ChatMessage.id.desc()).limit(1))


def _saved_summary(
    db: Session, assistant_id: int, fallback: dict[str, Any]
) -> dict[str, Any]:
    """读取该条回复完成时保存的需求摘要；老数据无明细时回退到当前会话摘要。"""
    run = db.scalar(
        select(AgentRun)
        .where(
            AgentRun.message_id == assistant_id,
            AgentRun.agent_code == "product_understanding",
        )
        .order_by(AgentRun.id.desc())
        .limit(1)
    )
    if run is not None and run.output_full:
        try:
            output = json.loads(run.output_full)
            summary = output.get("requirement_summary")
            if isinstance(summary, dict):
                return summary
        except (TypeError, ValueError):
            pass
    return fallback


def _write_agent_runs(
    db: Session,
    *,
    session_id: int,
    message_id: int,
    context_text: str,
    runs: list[dict[str, Any]],
) -> None:
    """按给定明细写入规划与商品理解两条 Agent 调用记录。"""
    for run in runs:
        output = run.get("output")
        output_text = (
            json.dumps(output, ensure_ascii=False) if output is not None else None
        )
        db.add(
            AgentRun(
                session_id=session_id,
                message_id=message_id,
                agent_code=run["agent_code"],
                status=run["status"],
                model_name=run.get("model_name"),
                input_summary=context_text[:200] if context_text else None,
                output_summary=(output_text or "")[:200] or None,
                input_full=context_text or None,
                output_full=output_text,
                prompt_tokens=int(run.get("prompt_tokens", 0) or 0),
                completion_tokens=int(run.get("completion_tokens", 0) or 0),
                latency_ms=run.get("latency_ms", 0),
                error_message=run.get("error_message"),
            )
        )


def _mark_failed(message_id: int) -> None:
    """把仍处于 sending 的 Agent 回复标记为 failed。"""
    try:
        with SessionLocal() as write_db:
            assistant = write_db.get(ChatMessage, message_id)
            if assistant is not None and assistant.status == "sending":
                assistant.status = "failed"
                write_db.commit()
                print(f"[SSE] 连接中断，消息标记失败 message_id={message_id}")
    except Exception:
        pass


def _stream_reply(
    *,
    session_id: int,
    assistant_id: int,
    user_content: str,
    params: ChatParams,
) -> Iterator[str]:
    """输出 SSE 事件，并在结束时落库；断线时把未完成消息标记为 failed。"""
    completed = False
    context_text = ""
    planner_output: PlannerOutput | None = None
    product_output: ProductStream | None = None
    try:
        # 读取会话并组装上下文；当前 assistant 占位不进入上下文
        with SessionLocal() as read_db:
            session = read_db.get(CreativeSession, session_id)
            if session is None:
                raise ModelCallError("会话不存在")
            context = build_context(
                read_db,
                session,
                params,
                rounds=settings.CHAT_CONTEXT_ROUNDS,
                exclude_message_id=assistant_id,
            )
        context_text = context_as_text(context)

        print(f"[SSE] 开始回复 session_id={session_id} message_id={assistant_id}")
        yield _sse(
            "meta",
            {
                "message_id": assistant_id,
                "session_id": session_id,
                "duplicate": False,
            },
        )

        yield _sse("agent_status", {"agent_code": "planner", "status": "started"})
        planner_output = run_planner(context, user_content)
        yield _sse("agent_status", {"agent_code": "planner", "status": "finished"})

        yield _sse("agent_status", {"agent_code": "product_understanding", "status": "started"})
        product_output = stream_product(context)
        for delta in product_output:
            yield _sse("delta", {"content": delta})
        yield _sse("agent_status", {"agent_code": "product_understanding", "status": "finished"})

        token_in = planner_output.prompt_tokens + product_output.prompt_tokens
        token_out = planner_output.completion_tokens + product_output.completion_tokens
        summary = product_output.summary

        # 流结束后写库：回复内容、需求摘要、需求变化判定与 Agent 调用明细
        with SessionLocal() as write_db:
            assistant = write_db.get(ChatMessage, assistant_id)
            # 回复最终返回时以 done 落库；即使期间被分页的惰性超时标记为 failed，
            # 也以实际完成的回复为准，避免出现 done 事件与数据库状态不一致。
            if assistant is not None:
                assistant.content = product_output.reply
                assistant.status = "done"
                assistant.token_in = token_in
                assistant.token_out = token_out

            chat_session = write_db.get(CreativeSession, session_id)
            if chat_session is not None:
                summary = merge_agent_summary(
                    chat_session.requirement_summary, product_output.summary
                )
                chat_session.requirement_summary = summary
                chat_session.last_message_at = datetime.now(timezone.utc)

            changed = compute_requirement_changed(write_db, session_id, params, summary)
            _write_agent_runs(
                write_db,
                session_id=session_id,
                message_id=assistant_id,
                context_text=context_text,
                runs=[
                    {
                        "agent_code": "planner",
                        "status": "success",
                        "model_name": planner_output.model_name,
                        "output": planner_output.plan,
                        "prompt_tokens": planner_output.prompt_tokens,
                        "completion_tokens": planner_output.completion_tokens,
                        "latency_ms": planner_output.latency_ms,
                    },
                    {
                        "agent_code": "product_understanding",
                        "status": "success",
                        "model_name": product_output.model_name,
                        "output": {
                            "reply": product_output.reply,
                            "requirement_summary": summary,
                        },
                        "prompt_tokens": product_output.prompt_tokens,
                        "completion_tokens": product_output.completion_tokens,
                        "latency_ms": product_output.latency_ms,
                    },
                ],
            )
            write_db.commit()
        completed = True

        yield _sse(
            "done",
            {
                "message_id": assistant_id,
                "token_in": token_in,
                "token_out": token_out,
                "requirement_summary": summary,
                "requirement_changed": changed,
            },
        )
        print(f"[SSE] 回复完成 session_id={session_id} message_id={assistant_id}")
    except Exception as exc:
        if completed:
            # 已经成功落库，仅剩 done 事件写出失败（如客户端断开），不再重复写失败明细
            raise
        print(f"[SSE] 回复失败 session_id={session_id} message_id={assistant_id}: {exc}")
        _mark_failed(assistant_id)
        try:
            with SessionLocal() as write_db:
                error_message = str(exc)[:500]
                runs: list[dict[str, Any]] = []
                if planner_output is not None:
                    runs.append(
                        {
                            "agent_code": "planner",
                            "status": "success",
                            "model_name": planner_output.model_name,
                            "output": planner_output.plan,
                            "prompt_tokens": planner_output.prompt_tokens,
                            "completion_tokens": planner_output.completion_tokens,
                            "latency_ms": planner_output.latency_ms,
                        }
                    )
                else:
                    runs.append(
                        {
                            "agent_code": "planner",
                            "status": "failed",
                            "model_name": (
                                settings.ARK_TEXT_MODEL if real_model_enabled() else None
                            ),
                            "error_message": error_message,
                        }
                    )
                runs.append(
                    {
                        "agent_code": "product_understanding",
                        "status": "failed",
                        "model_name": (
                            product_output.model_name
                            if product_output is not None
                            else (settings.ARK_TEXT_MODEL if real_model_enabled() else None)
                        ),
                        "prompt_tokens": (
                            product_output.prompt_tokens if product_output else 0
                        ),
                        "completion_tokens": (
                            product_output.completion_tokens if product_output else 0
                        ),
                        "latency_ms": product_output.latency_ms if product_output else 0,
                        "error_message": error_message,
                    }
                )
                _write_agent_runs(
                    write_db,
                    session_id=session_id,
                    message_id=assistant_id,
                    context_text=context_text,
                    runs=runs,
                )
                write_db.commit()
        except Exception:
            pass
        yield _sse("error", {"code": 30001, "message": "回复失败，请重试"})
    finally:
        if not completed:
            # 客户端断线或生成中异常：把仍处于 sending 的回复标记为失败，允许同幂等键重发
            _mark_failed(assistant_id)


def _replay_stream(
    db: Session,
    session: CreativeSession,
    assistant: ChatMessage,
    params: ChatParams,
) -> StreamingResponse:
    """已完成消息的重放：meta(duplicate=true) + 一次完整 delta + done。"""
    current_summary = session.requirement_summary or {}
    # done 返回该条回复完成时保存的摘要；requirement_changed 按当前状态重新计算
    summary = _saved_summary(db, assistant.id, current_summary)
    changed = compute_requirement_changed(db, session.id, params, current_summary)

    def generator() -> Iterator[str]:
        print(f"[SSE] 重放消息 session_id={session.id} message_id={assistant.id}")
        yield _sse(
            "meta",
            {
                "message_id": assistant.id,
                "session_id": session.id,
                "duplicate": True,
            },
        )
        yield _sse("delta", {"content": assistant.content})
        yield _sse(
            "done",
            {
                "message_id": assistant.id,
                "token_in": assistant.token_in,
                "token_out": assistant.token_out,
                "requirement_summary": summary,
                "requirement_changed": changed,
            },
        )

    return _streaming_response(generator())


def _duplicate_response(
    db: Session,
    session: CreativeSession,
    user_message: ChatMessage,
    *,
    params: ChatParams,
) -> StreamingResponse:
    """处理重复幂等键：已完成重放、处理中 409、失败则复用原回复重新生成。"""
    expire_stale_messages(db, session.id)
    assistant = _assistant_for_user_message(db, session.id, user_message.id)
    if assistant is None or assistant.status == "sending":
        raise ApiError(409, 30005, "消息正在处理中，请稍候")

    if assistant.status == "done":
        return _replay_stream(db, session, assistant, params)

    # 复用原 Agent 回复消息，不新增用户消息或回复消息。
    # 模型调用在 _stream_reply 内执行；失败时会统一标记 failed 并返回 error 事件。
    assistant.status = "sending"
    assistant.content = ""
    assistant.token_in = 0
    assistant.token_out = 0
    # 超时规则以 created_at 判断，重试时刷新处理时钟
    assistant.created_at = datetime.now(timezone.utc)
    session.last_message_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(assistant)

    return _streaming_response(
        _stream_reply(
            session_id=session.id,
            assistant_id=assistant.id,
            user_content=user_message.content,
            params=params,
        )
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
    width, height = validate_size(payload.params.width, payload.params.height)
    upload_ids = validate_upload_ids(db, auth.user.id, payload.params.upload_ids)
    params = ChatParams(
        product_name=product_name,
        style_text=style_text,
        width=width,
        height=height,
        template_id=payload.params.template_id,
        upload_ids=upload_ids,
    )

    requested_session_id = path_session_id if path_session_id is not None else payload.session_id

    # 进程内锁 + 数据库事务：避免首条消息并发创建两个会话，或并发插入重复消息
    with workspace_lock():
        session: CreativeSession | None = None
        if requested_session_id is not None:
            session = get_owned_session(db, auth.user.id, requested_session_id)
            expire_stale_messages(db, session.id)
            duplicate, _ = _find_duplicate(db, auth.user.id, session.id, client_message_id)
            if duplicate is not None:
                return _duplicate_response(db, session, duplicate, params=params)
        else:
            duplicate, existing_session = _find_duplicate(
                db, auth.user.id, None, client_message_id
            )
            if duplicate is not None and existing_session is not None:
                expire_stale_messages(db, existing_session.id)
                return _duplicate_response(
                    db, existing_session, duplicate, params=params
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
        db.flush()
        db.refresh(user_message)

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
            if duplicate is not None:
                if existing_session is None and requested_session_id is not None:
                    existing_session = get_owned_session(
                        db, auth.user.id, requested_session_id
                    )
                if existing_session is not None:
                    return _duplicate_response(
                        db, existing_session, duplicate, params=params
                    )
            raise
        db.refresh(assistant_message)
        session_id = session.id
        assistant_id = assistant_message.id

    return _streaming_response(
        _stream_reply(
            session_id=session_id,
            assistant_id=assistant_id,
            user_content=content,
            params=params,
        )
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
