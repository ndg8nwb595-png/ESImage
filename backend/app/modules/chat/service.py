"""3 号会话增量的校验、软删除与需求变化判定。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.response import ApiError
from app.models.workspace import ChatMessage, CreativeSession, UploadedAsset
from app.modules.chat.agents import ChatParams, latest_confirmed_sample
from app.modules.workspace.service import get_owned_session

MAX_SESSION_TITLE_LENGTH = 50
MAX_CHAT_UPLOAD_COUNT = 5


def validate_session_title(value: Any) -> str:
    """会话标题：去除首尾空格后 1~50 字符，纯空格与换行控制字符拒绝。"""
    if value is None:
        raise ApiError(400, 10002, "请输入会话名称")
    if not isinstance(value, str):
        raise ApiError(400, 10003, "参数格式错误")

    title = value.strip()
    if title == "":
        raise ApiError(400, 10002, "请输入会话名称")
    if len(title) > MAX_SESSION_TITLE_LENGTH:
        raise ApiError(400, 10004, "会话名称不能超过 50 个字符")
    if any(ord(char) < 32 or ord(char) == 127 for char in title):
        raise ApiError(400, 10003, "参数格式错误")
    return title


def rename_session(
    db: Session, user_id: int, session_id: int, title: Any
) -> CreativeSession:
    """重命名当前用户的活跃会话；不修改消息、生成批次与 last_message_at。"""
    session = get_owned_session(db, user_id, session_id)
    session.title = validate_session_title(title)
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session


def hide_session(db: Session, user_id: int, session_id: int) -> CreativeSession:
    """软删除会话：只把 status 置为 hidden，保留全部消息与生成记录。"""
    session = get_owned_session(db, user_id, session_id)
    session.status = "hidden"
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(session)
    return session


def expire_stale_messages(
    db: Session,
    session_id: int,
    *,
    threshold_seconds: int | None = None,
    now: datetime | None = None,
) -> int:
    """把超过阈值仍为 sending 的 Agent 消息惰性标记为 failed。

    用户消息不参与超时标记；返回本次标记的条数。
    """
    threshold = (
        settings.CHAT_MESSAGE_TIMEOUT_SECONDS
        if threshold_seconds is None
        else threshold_seconds
    )
    if threshold <= 0:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(seconds=threshold)
    stale = list(
        db.scalars(
            select(ChatMessage).where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
                ChatMessage.status == "sending",
                ChatMessage.created_at < cutoff,
            )
        )
    )
    if not stale:
        return 0
    for message in stale:
        message.status = "failed"
    db.commit()
    print(f"[会话] 惰性超时标记 session_id={session_id} count={len(stale)}")
    return len(stale)


def validate_upload_ids(
    db: Session, user_id: int, upload_ids: Any
) -> tuple[int, ...]:
    """聊天参数中的上传图：0~5 个，必须属于当前用户且 status=active。"""
    if upload_ids is None:
        return ()
    if not isinstance(upload_ids, list):
        raise ApiError(400, 10003, "参数格式错误")
    if len(upload_ids) > MAX_CHAT_UPLOAD_COUNT:
        raise ApiError(400, 30006, "上传文件不符合要求")

    ids: list[int] = []
    for raw in upload_ids:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ApiError(400, 10003, "参数格式错误")
        ids.append(raw)

    unique_ids = list(dict.fromkeys(ids))
    if not unique_ids:
        return ()
    owned = set(
        db.scalars(
            select(UploadedAsset.id).where(
                UploadedAsset.id.in_(unique_ids),
                UploadedAsset.user_id == user_id,
                UploadedAsset.status == "active",
            )
        )
    )
    if owned != set(unique_ids):
        raise ApiError(400, 30006, "上传文件不符合要求")
    return tuple(unique_ids)


def _normalize_style(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_points(value: Any) -> frozenset[str]:
    """卖点按去空格、去重后的集合比较，忽略顺序。"""
    if not isinstance(value, list):
        return frozenset()
    return frozenset(
        text.strip() for text in value if isinstance(text, str) and text.strip()
    )


def compute_requirement_changed(
    db: Session,
    session_id: int,
    params: ChatParams,
    summary: dict[str, Any] | None,
) -> bool:
    """比对最近一个已确认示例批次与当前需求。

    比对风格、卖点和尺寸；没有已确认示例批次时始终为 False。
    """
    batch = latest_confirmed_sample(db, session_id)
    if batch is None:
        return False

    if _normalize_style(params.style_text) != _normalize_style(batch.style_text):
        return True
    if params.width != batch.width or params.height != batch.height:
        return True

    batch_summary = (
        batch.requirement_summary if isinstance(batch.requirement_summary, dict) else {}
    )
    current_points = _normalize_points((summary or {}).get("selling_points"))
    batch_points = _normalize_points(batch_summary.get("selling_points"))
    return current_points != batch_points
