"""商品图上传、元数据恢复、软删除与文件读取。"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext
from app.core.response import ApiError, ok
from app.models.workspace import UploadedAsset
from app.modules.workspace.imaging import decode_image, make_thumbnail_webp
from app.modules.workspace.service import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    MAX_IMAGE_BYTES,
    MAX_UPLOAD_COUNT,
    media_response,
    require_permission,
    to_iso,
    upload_file_url,
    upload_thumbnail_url,
    workspace_lock,
)
from app.modules.workspace.storage import storage

router = APIRouter(tags=["workspace"])


def _upload_data(asset: UploadedAsset) -> dict:
    """上传图统一响应结构。"""
    return {
        "upload_id": asset.id,
        "file_url": upload_file_url(asset.id),
        "thumbnail_url": upload_thumbnail_url(asset.id),
        "width": asset.width,
        "height": asset.height,
        "size_bytes": asset.size_bytes,
        "mime_type": asset.mime_type,
        "original_name": asset.original_name,
        "sort_order": asset.sort_order,
        "status": asset.status,
        "created_at": to_iso(asset.created_at),
    }


def _get_owned_asset(db: Session, user_id: int, upload_id: int) -> UploadedAsset:
    asset = db.get(UploadedAsset, upload_id)
    if asset is None or asset.user_id != user_id or asset.status != "active":
        raise ApiError(404, 30014, "文件不存在")
    return asset


@router.post("/uploads")
async def upload_image(
    file: UploadFile = File(...),
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """上传单张商品图；后端二次校验格式、大小、可解码性与数量。"""
    original_name = file.filename or "upload"
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ApiError(400, 30006, "仅支持 JPG、PNG、WEBP 格式")

    mime_type = (file.content_type or "").lower()
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ApiError(400, 30006, "仅支持 JPG、PNG、WEBP 格式")

    if file.size is not None and file.size > MAX_IMAGE_BYTES:
        raise ApiError(400, 30006, "单张图片不能超过 10MB")

    data = await file.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise ApiError(400, 30006, "单张图片不能超过 10MB")

    try:
        width, height = decode_image(data)
    except ValueError as exc:
        raise ApiError(400, 30006, str(exc) or "图片文件损坏，请重新上传") from exc

    token = uuid.uuid4().hex
    file_path = f"uploads/{auth.user.id}/{token}{extension}"
    thumbnail_path = f"thumbnails/{auth.user.id}/{token}.webp"
    # MinIO 是同步网络调用，放到线程池避免阻塞事件循环
    await run_in_threadpool(storage.save, file_path, data)
    try:
        await run_in_threadpool(
            lambda: storage.save(thumbnail_path, make_thumbnail_webp(data))
        )
    except ValueError as exc:
        await run_in_threadpool(storage.delete, file_path)
        raise ApiError(400, 30006, str(exc) or "图片文件损坏，请重新上传") from exc
    except Exception:
        await run_in_threadpool(storage.delete, file_path)
        raise

    with workspace_lock():
        active_count = int(
            db.scalar(
                select(func.count())
                .select_from(UploadedAsset)
                .where(
                    UploadedAsset.user_id == auth.user.id,
                    UploadedAsset.session_id.is_(None),
                    UploadedAsset.status == "active",
                )
            )
            or 0
        )
        if active_count >= MAX_UPLOAD_COUNT:
            await run_in_threadpool(storage.delete, file_path)
            await run_in_threadpool(storage.delete, thumbnail_path)
            raise ApiError(400, 30006, "最多上传 5 张商品图")

        max_sort = db.scalar(
            select(func.max(UploadedAsset.sort_order)).where(
                UploadedAsset.user_id == auth.user.id,
                UploadedAsset.session_id.is_(None),
                UploadedAsset.status == "active",
            )
        )
        sort_order = (max_sort + 1) if max_sort is not None else 0

        asset = UploadedAsset(
            user_id=auth.user.id,
            session_id=None,
            file_path=file_path,
            thumbnail_path=thumbnail_path,
            original_name=str(original_name)[:255],
            mime_type=mime_type,
            size_bytes=len(data),
            width=width,
            height=height,
            sort_order=sort_order,
            status="active",
        )
        db.add(asset)
        try:
            db.commit()
        except Exception:
            db.rollback()
            await run_in_threadpool(storage.delete, file_path)
            await run_in_threadpool(storage.delete, thumbnail_path)
            raise
    db.refresh(asset)
    print(f"[上传] 用户 {auth.user.id} 上传商品图 upload_id={asset.id} sort={sort_order}")
    return ok(_upload_data(asset))


@router.get("/uploads/{upload_id}")
def get_upload(
    upload_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """读取上传图元数据，用于刷新后恢复。"""
    asset = _get_owned_asset(db, auth.user.id, upload_id)
    return ok(_upload_data(asset))


@router.delete("/uploads/{upload_id}")
def delete_upload(
    upload_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """软删除上传图；仅从当前创作中移除，已生成记录不受影响。"""
    asset = _get_owned_asset(db, auth.user.id, upload_id)
    asset.status = "deleted"
    db.commit()
    print(f"[上传] 用户 {auth.user.id} 软删除商品图 upload_id={upload_id}")
    return ok(None)


@router.get("/uploads/{upload_id}/content")
def get_upload_content(
    upload_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> Response:
    """读取上传图原图（demo 约定）。"""
    asset = _get_owned_asset(db, auth.user.id, upload_id)
    return media_response(
        asset.file_path,
        media_type=asset.mime_type,
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": "inline",
        },
    )


@router.get("/uploads/{upload_id}/thumbnail")
def get_upload_thumbnail(
    upload_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> Response:
    """读取上传图缩略图（demo 约定，WebP，最大宽度 400px）。"""
    asset = _get_owned_asset(db, auth.user.id, upload_id)
    if not asset.thumbnail_path:
        raise ApiError(404, 30014, "文件不存在")
    return media_response(
        asset.thumbnail_path,
        media_type="image/webp",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
        },
    )
