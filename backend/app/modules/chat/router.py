"""3 号增量接口：会话重命名与会话软删除。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext
from app.core.response import ok
from app.modules.chat.schemas import RenameSessionRequest
from app.modules.chat.service import hide_session, rename_session
from app.modules.workspace.service import require_permission, to_iso

router = APIRouter(tags=["chat"])


@router.patch("/sessions/{session_id}")
def rename(
    session_id: int,
    payload: RenameSessionRequest | None = None,
    auth: AuthContext = Depends(require_permission("user.workspace")),
    db: Session = Depends(get_db),
) -> dict:
    """重命名会话；不影响消息、生成批次与 last_message_at。"""
    session = rename_session(
        db,
        auth.user.id,
        session_id,
        payload.title if payload is not None else None,
    )
    return ok(
        {
            "session_id": session.id,
            "title": session.title,
            "status": session.status,
            "updated_at": to_iso(session.updated_at),
        }
    )


@router.delete("/sessions/{session_id}")
def delete(
    session_id: int,
    auth: AuthContext = Depends(require_permission("user.workspace")),
    db: Session = Depends(get_db),
) -> dict:
    """软删除会话；消息与生成记录保留，管理员仍可追溯。"""
    session = hide_session(db, auth.user.id, session_id)
    return ok({"session_id": session.id, "status": session.status})
