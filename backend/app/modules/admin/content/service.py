"""内容追溯的序列化与媒体读取。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.deps import AuthContext
from app.core.response import ApiError
from app.models.user import User
from app.models.workspace import CreativeSession, GeneratedImage, GenerationBatch
from app.modules.admin.service import (
    archive_path_for,
    bytes_response,
    content_disposition,
    ensure_content_access,
    file_response,
    image_download_url,
    image_preview_url,
    image_thumbnail_url,
    media_type_for,
    read_storage_bytes,
    safe_filename_part,
    filename_timestamp,
    to_iso,
)

ARCHIVE_UNAVAILABLE_MESSAGE = "文件归档中，请稍后重试"


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise ApiError(404, 30017, "用户不存在")
    return user


def get_session_or_404(db: Session, session_id: int) -> CreativeSession:
    session = db.get(CreativeSession, session_id)
    if session is None:
        raise ApiError(404, 30013, "会话不存在")
    return session


def get_batch_or_404(db: Session, batch_id: int) -> GenerationBatch:
    batch = db.get(GenerationBatch, batch_id)
    if batch is None:
        raise ApiError(404, 30004, "批次不存在")
    return batch


def get_image_or_404(db: Session, image_id: int) -> GeneratedImage:
    image = db.get(GeneratedImage, image_id)
    if image is None:
        raise ApiError(404, 30024, "图片不存在")
    return image


def get_media_image(db: Session, auth: AuthContext, image_id: int) -> GeneratedImage:
    """媒体访问统一的图片存在性与超管内容边界校验。"""
    image = get_image_or_404(db, image_id)
    ensure_content_access(db, auth, image.user_id)
    return image


def serialize_content_user(
    user: User, last_generated_at, batch_count: int
) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "status": user.status,
        "last_generated_at": to_iso(last_generated_at),
        "batch_count": int(batch_count),
    }


def serialize_session(
    session: CreativeSession, batch_count: int, latest_batch_at
) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "title": session.title,
        "status": session.status,
        "last_message_at": to_iso(session.last_message_at),
        "batch_count": int(batch_count),
        "latest_batch_at": to_iso(latest_batch_at),
        "created_at": to_iso(session.created_at),
    }


def serialize_batch(batch: GenerationBatch) -> dict[str, Any]:
    """批次列表项；图片构成按计划口径。"""
    if batch.batch_type == "sample":
        composition = {"main": 1, "detail": 0}
    else:
        composition = {"main": 1, "detail": max(0, batch.total_count - 1)}
    return {
        "batch_id": batch.id,
        "batch_type": batch.batch_type,
        "status": batch.status,
        "product_name": batch.product_name,
        "style_text": batch.style_text,
        "width": batch.width,
        "height": batch.height,
        "template_name": batch.template_name,
        "total_count": batch.total_count,
        "completed_count": batch.completed_count,
        "composition": composition,
        "created_at": to_iso(batch.created_at),
        "finished_at": to_iso(batch.finished_at),
    }


def serialize_image_item(image: GeneratedImage) -> dict[str, Any]:
    return {
        "image_id": image.id,
        "index_no": image.index_no,
        "attempt_no": image.attempt_no,
        "image_role": image.image_role,
        "status": image.status,
        "width": image.width,
        "height": image.height,
        "thumbnail_url": image_thumbnail_url(image.id) if image.thumbnail_path else None,
        "archived_at": to_iso(image.archived_at),
        "is_history_visible": bool(image.is_history_visible),
        "created_at": to_iso(image.created_at),
    }


def serialize_image_detail(
    db: Session, image: GeneratedImage
) -> dict[str, Any]:
    """单图详情；所有字段均返回，空值为 null。"""
    batch = db.get(GenerationBatch, image.batch_id)
    session = db.get(CreativeSession, image.session_id) if image.session_id else None
    user = db.get(User, image.user_id)

    if batch is None:
        raise ApiError(404, 30004, "批次不存在")
    if session is None:
        raise ApiError(404, 30013, "会话不存在")
    if user is None:
        raise ApiError(404, 30017, "用户不存在")

    has_file = bool(image.file_path)
    return {
        "image_id": image.id,
        "batch_id": image.batch_id,
        "batch_type": batch.batch_type,
        "batch_status": batch.status,
        "session_id": image.session_id,
        "session_title": session.title,
        "user_id": image.user_id,
        "username": user.username,
        "display_name": user.display_name,
        "index_no": image.index_no,
        "attempt_no": image.attempt_no,
        "image_type": image.image_type,
        "image_role": image.image_role,
        "status": image.status,
        "product_name": batch.product_name,
        "style_text": batch.style_text,
        "width": image.width,
        "height": image.height,
        "template_name": batch.template_name,
        "prompt": image.prompt,
        "negative_prompt": image.negative_prompt,
        "model_name": image.model_name,
        "latency_ms": image.latency_ms,
        "prompt_tokens": image.prompt_tokens,
        "completion_tokens": image.completion_tokens,
        "error_message": image.error_message,
        "created_at": to_iso(image.created_at),
        "file_path": image.file_path,
        "is_history_visible": bool(image.is_history_visible),
        "archived_at": to_iso(image.archived_at),
        "thumbnail_url": image_thumbnail_url(image.id) if image.thumbnail_path else None,
        "preview_url": image_preview_url(image.id) if has_file else None,
        "download_url": image_download_url(image.id) if has_file else None,
    }


def thumbnail_response(image: GeneratedImage):
    """缩略图始终从热存储读取，不因归档切换路径。"""
    if not image.thumbnail_path:
        raise ApiError(404, 30014, "文件不存在")
    return file_response(
        image.thumbnail_path,
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": "inline",
        },
    )


def _content_filename(image: GeneratedImage, batch: GenerationBatch | None) -> str:
    role_label = "主图" if image.image_role == "main" else "详情图"
    product_name = batch.product_name if batch else ""
    return (
        f"{safe_filename_part(product_name)}_{role_label}_"
        f"{image.index_no}_{filename_timestamp(image.created_at)}.png"
    )


def content_response(image: GeneratedImage):
    """大图预览：归档图从 archive/ 读取并限制超时。"""
    if not image.file_path:
        raise ApiError(404, 30014, "文件不存在")

    filename = f"{image.index_no}_{image.id}.png"
    headers = {
        "Content-Disposition": content_disposition(filename, inline=True),
        "Cache-Control": "private, no-store",
    }
    if image.archived_at is not None:
        data = read_storage_bytes(
            archive_path_for(image.file_path),
            archive_message=ARCHIVE_UNAVAILABLE_MESSAGE,
        )
        return bytes_response(
            data, media_type=media_type_for(image.file_path), headers=headers
        )
    return file_response(image.file_path, headers=headers)


def download_response(db: Session, image: GeneratedImage):
    """下载原图；归档图从 archive/ 读取并限制超时。"""
    if not image.file_path:
        raise ApiError(404, 30014, "文件不存在")

    batch = db.get(GenerationBatch, image.batch_id)
    filename = _content_filename(image, batch)
    headers = {
        "Content-Disposition": content_disposition(filename, inline=False),
        "Cache-Control": "private, no-store",
    }
    if image.archived_at is not None:
        data = read_storage_bytes(
            archive_path_for(image.file_path),
            archive_message=ARCHIVE_UNAVAILABLE_MESSAGE,
        )
        return bytes_response(
            data, media_type=media_type_for(image.file_path), headers=headers
        )
    return file_response(image.file_path, headers=headers)
