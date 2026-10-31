"""内容追溯与聊天记录（7/8 号 PRD 最小 demo）。"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.config import SystemPrompt
from app.models.user import User
from app.models.workspace import AgentRun, ChatMessage, CreativeSession, GeneratedImage, GenerationBatch
from app.modules.workspace.service import to_iso
from app.modules.workspace.storage import storage

router = APIRouter(tags=["admin-content"])


def _is_super(user: User) -> bool:
    return any(r.code == "super_admin" for r in user.roles)


def _check_content_user(auth: AuthContext, db: Session, user_id: int) -> None:
    """管理员不能查看超管账号内容。"""
    if _is_super(auth.user):
        return
    user = db.get(User, user_id)
    if user is not None and _is_super(user):
        raise ApiError(403, 20006, "无权查看超管账号内容")


def _image_file_relative_path(image: GeneratedImage) -> str | None:
    if not image.file_path:
        return None
    if image.archived_at is not None:
        return f"archive/{image.file_path}"
    return image.file_path


def _get_owned_image(db: Session, image_id: int) -> GeneratedImage:
    image = db.get(GeneratedImage, image_id)
    if image is None:
        raise ApiError(404, 30024, "图片不存在")
    return image


def _parse_day(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ApiError(400, 10003, "日期格式不合法") from None
    return datetime.combine(day, time.min, tzinfo=settings.TZ).astimezone(timezone.utc)


# ---- 内容追溯：用户 -> 会话 -> 批次 -> 图片 ----

@router.get("/content/users")
def content_users(
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """有生成记录的用户。"""
    kw = (keyword or "").strip()
    filters = []
    if kw:
        filters.append(or_(User.username.ilike(f"%{kw}%"), User.display_name.ilike(f"%{kw}%")))
    if not _is_super(auth.user):
        filters.append(~User.roles.any(code="super_admin"))

    subq = select(User.id).where(*filters)
    batch_user = select(GenerationBatch.user_id.distinct()).where(GenerationBatch.user_id.in_(subq))
    base = select(User).where(User.id.in_(batch_user))
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    users = list(
        db.scalars(base.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size))
    )

    items = []
    for u in users:
        last_generated = db.scalar(
            select(func.max(GenerationBatch.created_at)).where(GenerationBatch.user_id == u.id)
        )
        batch_count = int(
            db.scalar(select(func.count()).select_from(GenerationBatch).where(GenerationBatch.user_id == u.id)) or 0
        )
        items.append(
            {
                "user_id": u.id,
                "username": u.username,
                "display_name": u.display_name,
                "status": u.status,
                "last_generated_at": to_iso(last_generated),
                "batch_count": batch_count,
            }
        )
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/content/users/{user_id}/sessions")
def content_user_sessions(
    user_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """用户会话列表。"""
    _check_content_user(auth, db, user_id)
    base = select(CreativeSession).where(CreativeSession.user_id == user_id)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    sessions = list(
        db.scalars(
            base.order_by(CreativeSession.last_message_at.desc().nulls_last(), CreativeSession.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    items = []
    for s in sessions:
        batch_count = int(
            db.scalar(select(func.count()).select_from(GenerationBatch).where(GenerationBatch.session_id == s.id)) or 0
        )
        latest_batch_at = db.scalar(
            select(func.max(GenerationBatch.created_at)).where(GenerationBatch.session_id == s.id)
        )
        items.append(
            {
                "session_id": s.id,
                "title": s.title,
                "status": s.status,
                "last_message_at": to_iso(s.last_message_at),
                "batch_count": batch_count,
                "latest_batch_at": to_iso(latest_batch_at),
                "created_at": to_iso(s.created_at),
            }
        )
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/content/sessions/{session_id}/batches")
def content_session_batches(
    session_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """会话批次列表。"""
    session = db.get(CreativeSession, session_id)
    if session is None:
        raise ApiError(404, 30013, "会话不存在")
    _check_content_user(auth, db, session.user_id)

    base = select(GenerationBatch).where(GenerationBatch.session_id == session_id)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    batches = list(
        db.scalars(base.order_by(GenerationBatch.created_at.desc(), GenerationBatch.id.desc()).offset((page - 1) * page_size).limit(page_size))
    )
    items = [
        {
            "batch_id": b.id,
            "batch_type": b.batch_type,
            "status": b.status,
            "product_name": b.product_name,
            "style_text": b.style_text,
            "width": b.width,
            "height": b.height,
            "template_name": b.template_name,
            "total_count": b.total_count,
            "completed_count": b.completed_count,
            "composition": {"main": 1, "detail": b.total_count - 1},
            "created_at": to_iso(b.created_at),
            "finished_at": to_iso(b.finished_at),
        }
        for b in batches
    ]
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/content/batches/{batch_id}/images")
def content_batch_images(
    batch_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """批次图片列表。"""
    batch = db.get(GenerationBatch, batch_id)
    if batch is None:
        raise ApiError(404, 30004, "批次不存在")
    _check_content_user(auth, db, batch.user_id)

    base = select(GeneratedImage).where(GeneratedImage.batch_id == batch_id)
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    images = list(
        db.scalars(base.order_by(GeneratedImage.index_no.asc(), GeneratedImage.attempt_no.desc(), GeneratedImage.id.desc()).offset((page - 1) * page_size).limit(page_size))
    )
    items = [
        {
            "image_id": img.id,
            "index_no": img.index_no,
            "attempt_no": img.attempt_no,
            "image_role": img.image_role,
            "status": img.status,
            "width": img.width,
            "height": img.height,
            "thumbnail_url": f"/api/v1/admin/content/images/{img.id}/thumbnail" if img.thumbnail_path else None,
            "archived_at": to_iso(img.archived_at),
            "is_history_visible": img.is_history_visible,
            "created_at": to_iso(img.created_at),
        }
        for img in images
    ]
    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/content/images/{image_id}")
def content_image_detail(
    image_id: int,
    auth: AuthContext = Depends(require_permission("admin.content.view")),
    db: Session = Depends(get_db),
) -> dict:
    """单图详情。"""
    image = _get_owned_image(db, image_id)
    _check_content_user(auth, db, image.user_id)
    batch = db.get(GenerationBatch, image.batch_id)
    session = db.get(CreativeSession, image.session_id)
    user = db.get(User, image.user_id)
    return ok(
        {
            "image_id": image.id,
            "batch_id": image.batch_id,
            "batch_type": batch.batch_type if batch else None,
            "batch_status": batch.status if batch else None,
            "session_id": image.session_id,
            "session_title": session.title if session else None,
            "user_id": image.user_id,
            "username": user.username if user else None,
            "display_name": user.display_name if user else None,
            "index_no": image.index_no,
            "attempt_no": image.attempt_no,
            "image_type": image.image_type,
            "image_role": image.image_role,
            "status": image.status,
            "product_name": batch.product_name if batch else None,
            "style_text": batch.style_text if batch else None,
            "width": image.width,
            "height": image.height,
            "template_name": batch.template_name if batch else None,
            "prompt": image.prompt,
            "negative_prompt": image.negative_prompt,
            "model_name": image.model_name,
            "latency_ms": image.latency_ms,
            "prompt_tokens": image.prompt_tokens,
            "completion_tokens": image.completion_tokens,
            "error_message": image.error_message,
            "created_at": to_iso(image.created_at),
            "file_path": image.file_path,
            "is_history_visible": image.is_history_visible,
            "archived_at": to_iso(image.archived_at),
            "thumbnail_url": f"/api/v1/admin/content/images/{image.id}/thumbnail" if image.thumbnail_path else None,
            "preview_url": f"/api/v1/admin/content/images/{image.id}/content" if image.file_path else None,
            "download_url": f"/api/v1/admin/content/images/{image.id}/download" if image.file_path else None,
        }
    )


def _serve_media(image_id: int, kind: str, auth: AuthContext, db: Session) -> FileResponse:
    image = _get_owned_image(db, image_id)
    _check_content_user(auth, db, image.user_id)
    if kind == "thumbnail":
        relative = image.thumbnail_path
        mime = "image/webp"
    else:
        relative = _image_file_relative_path(image)
        mime = "image/png"
    if not relative:
        raise ApiError(404, 30014, "文件不存在")
    path = storage.path(relative)
    if not path.is_file():
        raise ApiError(404, 30014, "文件不存在")
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, max-age=300", "Content-Disposition": "inline"})


@router.get("/content/images/{image_id}/thumbnail")
def content_image_thumbnail(image_id: int, auth: AuthContext = Depends(require_permission("admin.content.view")), db: Session = Depends(get_db)):
    return _serve_media(image_id, "thumbnail", auth, db)


@router.get("/content/images/{image_id}/content")
def content_image_content(image_id: int, auth: AuthContext = Depends(require_permission("admin.content.view")), db: Session = Depends(get_db)):
    return _serve_media(image_id, "content", auth, db)


@router.get("/content/images/{image_id}/download")
def content_image_download(image_id: int, auth: AuthContext = Depends(require_permission("admin.content.view")), db: Session = Depends(get_db)):
    return _serve_media(image_id, "content", auth, db)


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
