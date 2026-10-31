"""内容追溯：用户 -> 会话 -> 批次 -> 图片（7 号 PRD 最小 demo）。

聊天记录接口已迁移到 `app.modules.admin.chat_records`（8 号 PRD）。
"""

from __future__ import annotations

from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.user import User
from app.models.workspace import CreativeSession, GeneratedImage, GenerationBatch
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
