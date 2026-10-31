"""数据链路契约（10 号 §4.6~§4.11 的应用层约束，接口文档 §2.8）。

提供可被业务模块复用的数据层能力：会话/消息/Agent 调用写入（幂等、并发去重、
稳定排序、脱敏）与批次/图片写入（类型/状态校验、角色组合、状态流转、历史可见性）。
本模块不实现 HTTP 与生成管线。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.redact import redact
from app.models.workspace import (
    AgentRun,
    ChatMessage,
    CreativeSession,
    GeneratedImage,
    GenerationBatch,
)

# 批次类型允许的状态
SAMPLE_BATCH_STATUSES = {"queued", "running", "sample_ready", "confirmed", "failed", "cancelled"}
FULL_BATCH_STATUSES = {"queued", "running", "completed", "partially_failed", "failed", "cancelled"}

# 图片状态机：当前 -> 允许的下一状态
IMAGE_TRANSITIONS = {
    "pending": {"generating"},
    "generating": {"success", "failed", "cancelled"},
    "success": {"superseded"},
    "failed": {"superseded"},
    "cancelled": set(),
    "superseded": set(),
}

AGENT_CODES = {
    "planner", "product_understanding", "copywriter", "prompt_builder",
    "image_generator", "quality_reviewer", "repairer", "platform_rule",
}


class DataLinkError(Exception):
    """数据链路约束违反（中文原因）。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---- 会话与消息 ----

def create_session(db: Session, user_id: int, title: str) -> CreativeSession:
    session = CreativeSession(user_id=user_id, title=title, status="active")
    db.add(session)
    db.flush()
    return session


def _find_message(db: Session, session_id: int, client_message_id: str | None) -> ChatMessage | None:
    if not client_message_id:
        return None
    return db.scalar(
        select(ChatMessage).where(
            ChatMessage.session_id == session_id,
            ChatMessage.client_message_id == client_message_id,
        )
    )


def write_message(
    db: Session,
    session_id: int,
    *,
    role: str,
    content: str,
    client_message_id: str | None = None,
    agent_code: str | None = None,
    content_type: str = "text",
    token_in: int = 0,
    token_out: int = 0,
    status: str = "done",
) -> ChatMessage:
    """写入消息；同一 ``(session_id, client_message_id)`` 幂等返回已存在消息。"""
    existing = _find_message(db, session_id, client_message_id)
    if existing is not None:
        return existing

    message = ChatMessage(
        session_id=session_id,
        role=role,
        agent_code=agent_code,
        content=content,
        content_type=content_type,
        client_message_id=client_message_id,
        token_in=token_in,
        token_out=token_out,
        status=status,
    )
    db.add(message)
    db.flush()

    session = db.get(CreativeSession, session_id)
    if session is not None:
        session.last_message_at = message.created_at or _now()
    return message


def create_first_message(
    db: Session,
    *,
    user_id: int,
    title: str,
    role: str,
    content: str,
    client_message_id: str,
) -> ChatMessage:
    """并发安全地创建首条消息：相同 ``(user_id, client_message_id)`` 只建一个会话。

    使用 PostgreSQL 咨询锁（事务级）去重，不依赖 Redis。
    """
    lock_key = f"{user_id}:{client_message_id}"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": lock_key})

    # 锁内：查找该用户是否已有携带此 client_message_id 的消息
    existing = db.scalar(
        select(ChatMessage).join(CreativeSession, ChatMessage.session_id == CreativeSession.id)
        .where(
            CreativeSession.user_id == user_id,
            ChatMessage.client_message_id == client_message_id,
        )
    )
    if existing is not None:
        return existing

    session = create_session(db, user_id, title)
    message = write_message(
        db, session.id, role=role, content=content, client_message_id=client_message_id
    )
    db.commit()
    return message


def list_messages(db: Session, session_id: int) -> list[ChatMessage]:
    """按 ``(created_at, id)`` 稳定排序返回消息。"""
    return list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        )
    )


def record_agent_run(
    db: Session,
    *,
    agent_code: str,
    status: str,
    session_id: int | None = None,
    message_id: int | None = None,
    batch_id: int | None = None,
    image_id: int | None = None,
    model_name: str | None = None,
    input_summary: str | None = None,
    output_summary: str | None = None,
    input_full: str | None = None,
    output_full: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int | None = None,
    error_message: str | None = None,
) -> AgentRun:
    """记录一次 Agent 调用；输入输出落库前脱敏。"""
    run = AgentRun(
        agent_code=agent_code,
        status=status,
        session_id=session_id,
        message_id=message_id,
        batch_id=batch_id,
        image_id=image_id,
        model_name=model_name,
        input_summary=redact(input_summary),
        output_summary=redact(output_summary),
        input_full=redact(input_full),
        output_full=redact(output_full),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        error_message=error_message,
    )
    db.add(run)
    db.flush()
    return run


# ---- 批次与图片 ----

def validate_batch_status(batch_type: str, status: str) -> None:
    allowed = SAMPLE_BATCH_STATUSES if batch_type == "sample" else FULL_BATCH_STATUSES
    if status not in allowed:
        raise DataLinkError(f"{batch_type} 批次不允许状态 {status}")


def create_batch(
    db: Session,
    *,
    user_id: int,
    session_id: int,
    batch_type: str,
    product_name: str,
    width: int,
    height: int,
    total_count: int,
    params_snapshot: dict,
    source_sample_batch_id: int | None = None,
    style_text: str | None = None,
    template_name: str | None = None,
    client_request_id: str | None = None,
) -> GenerationBatch:
    """创建批次；``full`` 必须引用已存在的 ``sample`` 批次。"""
    if batch_type == "sample":
        if source_sample_batch_id is not None:
            raise DataLinkError("sample 批次不得引用示例批次")
    elif batch_type == "full":
        if source_sample_batch_id is None:
            raise DataLinkError("full 批次必须引用示例批次")
        source = db.get(GenerationBatch, source_sample_batch_id)
        if source is None or source.batch_type != "sample":
            raise DataLinkError("full 批次引用的必须是 sample 批次")

    if client_request_id:
        existing = db.scalar(
            select(GenerationBatch).where(
                GenerationBatch.client_request_id == client_request_id
            )
        )
        if existing is not None:
            return existing

    batch = GenerationBatch(
        user_id=user_id,
        session_id=session_id,
        batch_type=batch_type,
        source_sample_batch_id=source_sample_batch_id,
        product_name=product_name,
        style_text=style_text,
        width=width,
        height=height,
        template_name=template_name,
        total_count=total_count,
        status="queued",
        params_snapshot=params_snapshot,
        client_request_id=client_request_id,
    )
    db.add(batch)
    db.flush()
    return batch


def create_images(
    db: Session,
    batch: GenerationBatch,
    *,
    index_from: int = 1,
) -> list[GeneratedImage]:
    """按批次类型创建图片：示例批次 1 张 ``main``；全套批次 1 张 ``main`` + 5 张 ``detail``。"""
    images: list[GeneratedImage] = []
    if batch.batch_type == "sample":
        roles = [("main", 1)]
        image_type = "sample"
    else:
        roles = [("main", 1)] + [("detail", i) for i in range(2, 7)]
        image_type = "final"

    index_no = index_from
    for role, _count in roles:
        image = GeneratedImage(
            batch_id=batch.id,
            user_id=batch.user_id,
            session_id=batch.session_id,
            image_type=image_type,
            image_role=role,
            index_no=index_no,
            attempt_no=1,
            status="pending",
        )
        db.add(image)
        images.append(image)
        index_no += 1
    db.flush()
    return images


def transition_image(db: Session, image: GeneratedImage, new_status: str) -> None:
    """校验并流转图片状态；非法流转抛 :class:`DataLinkError`。"""
    if new_status not in IMAGE_TRANSITIONS.get(image.status, set()):
        raise DataLinkError(f"图片状态不允许从 {image.status} 流转到 {new_status}")
    image.status = new_status
    db.flush()


def history_visible(batch: GenerationBatch, image: GeneratedImage) -> bool:
    """判断图片是否可进入历史作品：full 批次 + final + success + 批次 completed/partially_failed。"""
    return (
        batch.batch_type == "full"
        and image.image_type == "final"
        and image.status == "success"
        and batch.status in ("completed", "partially_failed")
    )
