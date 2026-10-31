"""历史作品：只读列表、批次详情、整组 ZIP（5 号 PRD 最小 demo）。

单张下载复用 workspace 的 /images/{image_id}/download；本模块负责历史列表、详情与整组下载。
"""

from __future__ import annotations

import csv
import io
import zipfile
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext, require_permission
from app.core.response import ApiError, ok
from app.models.workspace import GeneratedImage, GenerationBatch
from app.modules.workspace.service import (
    filename_timestamp,
    image_content_url,
    image_thumbnail_url,
    safe_filename_part,
    to_iso,
)
from app.modules.workspace.storage import storage

router = APIRouter(tags=["history"])

HISTORY_STATUSES = ("completed", "partially_failed")


def _is_history_visible(image: GeneratedImage) -> bool:
    """历史可见条件（接口文档 §2.2）。"""
    return image.image_type == "final" and image.status == "success" and image.is_history_visible


def _latest_image_by_index(images: list[GeneratedImage]) -> dict[int, GeneratedImage]:
    """每个 index_no 取 attempt_no 最大、id 最大的一条（接口文档 §9.5）。"""
    result: dict[int, GeneratedImage] = {}
    for image in images:
        current = result.get(image.index_no)
        if current is None or (image.attempt_no, image.id) > (current.attempt_no, current.id):
            result[image.index_no] = image
    return result


def _image_file_path(image: GeneratedImage) -> str | None:
    """归档件读 archive/ 前缀，否则读原路径（接口文档 §11）。"""
    if not image.file_path:
        return None
    if image.archived_at is not None:
        return f"archive/{image.file_path}"
    return image.file_path


def _read_image_bytes(image: GeneratedImage) -> bytes:
    """读取图片文件；归档不可用返回 404 30014。"""
    relative_path = _image_file_path(image)
    if relative_path is None:
        raise ApiError(404, 30014, "文件不存在")
    path = storage.path(relative_path)
    if not path.is_file():
        message = "文件归档中，请稍后重试" if image.archived_at is not None else "文件不存在"
        raise ApiError(404, 30014, message)
    return path.read_bytes()


@router.get("/history")
def list_history(
    page: int = Query(1, ge=1),
    auth: AuthContext = Depends(require_permission("user.history")),
    db: Session = Depends(get_db),
) -> dict:
    """历史批次分页，每页固定 20 条，按批次生成时间倒序。"""
    page_size = 20
    # 只统计至少含一张历史可见成功图的 full 批次
    visible_batch_ids = (
        select(GeneratedImage.batch_id)
        .where(
            GeneratedImage.user_id == auth.user.id,
            GeneratedImage.image_type == "final",
            GeneratedImage.status == "success",
            GeneratedImage.is_history_visible.is_(True),
        )
        .distinct()
    )
    base = select(GenerationBatch).where(
        GenerationBatch.user_id == auth.user.id,
        GenerationBatch.batch_type == "full",
        GenerationBatch.status.in_(HISTORY_STATUSES),
        GenerationBatch.id.in_(visible_batch_ids),
    )
    total = int(db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    batches = list(
        db.scalars(
            base.order_by(GenerationBatch.created_at.desc(), GenerationBatch.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )

    images_by_batch: dict[int, list[GeneratedImage]] = {}
    if batches:
        images = list(
            db.scalars(
                select(GeneratedImage)
                .where(GeneratedImage.batch_id.in_([b.id for b in batches]))
                .order_by(GeneratedImage.batch_id, GeneratedImage.index_no.asc())
            )
        )
        for image in images:
            images_by_batch.setdefault(image.batch_id, []).append(image)

    items = []
    for batch in batches:
        latest = _latest_image_by_index(images_by_batch.get(batch.id, []))
        success_images = sorted(
            (img for img in latest.values() if _is_history_visible(img)),
            key=lambda img: img.index_no,
        )
        cover = success_images[0]
        items.append(
            {
                "batch_id": batch.id,
                "product_name": batch.product_name,
                "main_count": 1,
                "detail_count": batch.total_count - 1,
                "success_count": len(success_images),
                "total_count": batch.total_count,
                "cover_image_id": cover.id,
                "cover_thumbnail_url": image_thumbnail_url(cover.id),
                "created_at": to_iso(batch.created_at),
            }
        )

    return ok({"items": items, "total": total, "page": page, "page_size": page_size})


@router.get("/history/{batch_id}")
def get_history_detail(
    batch_id: int,
    auth: AuthContext = Depends(require_permission("user.history")),
    db: Session = Depends(get_db),
) -> dict:
    """批次详情与成功图片列表（接口文档 §5）。"""
    batch = db.get(GenerationBatch, batch_id)
    if batch is None:
        raise ApiError(404, 30004, "批次不存在")
    if batch.user_id != auth.user.id:
        raise ApiError(403, 20005, "无权限")
    if batch.batch_type != "full" or batch.status not in HISTORY_STATUSES:
        raise ApiError(404, 30004, "批次不存在")

    images = list(
        db.scalars(
            select(GeneratedImage)
            .where(GeneratedImage.batch_id == batch.id)
            .order_by(
                GeneratedImage.index_no.asc(),
                GeneratedImage.attempt_no.desc(),
                GeneratedImage.id.desc(),
            )
        )
    )
    latest = _latest_image_by_index(images)
    success_images = sorted(
        (img for img in latest.values() if _is_history_visible(img)),
        key=lambda img: img.index_no,
    )

    return ok(
        {
            "batch_id": batch.id,
            "product_name": batch.product_name,
            "style_text": batch.style_text,
            "width": batch.width,
            "height": batch.height,
            "main_count": 1,
            "detail_count": batch.total_count - 1,
            "success_count": len(success_images),
            "total_count": batch.total_count,
            "status": batch.status,
            "created_at": to_iso(batch.created_at),
            "images": [
                {
                    "image_id": img.id,
                    "index": img.index_no,
                    "image_role": img.image_role,
                    "width": img.width,
                    "height": img.height,
                    "thumbnail_url": image_thumbnail_url(img.id),
                    "content_url": image_content_url(img.id),
                    "created_at": to_iso(img.created_at),
                }
                for img in success_images
            ],
        }
    )


@router.get("/batches/{batch_id}/download")
def download_batch_zip(
    batch_id: int,
    auth: AuthContext = Depends(require_permission("user.history")),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """整组 ZIP + manifest.csv（接口文档 §9）。"""
    batch = db.get(GenerationBatch, batch_id)
    if batch is None:
        raise ApiError(404, 30004, "批次不存在")
    if batch.user_id != auth.user.id:
        raise ApiError(403, 20005, "无权限")
    if batch.batch_type != "full" or batch.status not in HISTORY_STATUSES:
        raise ApiError(409, 30005, "当前批次不可下载")

    images = list(
        db.scalars(select(GeneratedImage).where(GeneratedImage.batch_id == batch.id))
    )
    latest = _latest_image_by_index(images)

    product = safe_filename_part(batch.product_name)
    zip_filename = f"{product}_全套_{filename_timestamp(batch.created_at)}.zip"

    rows: list[list[str]] = [["序号", "文件名", "状态", "宽度", "高度", "生成时间", "失败原因"]]
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for index_no in range(1, batch.total_count + 1):
            image = latest.get(index_no)
            if image is not None and _is_history_visible(image):
                role_label = "主图" if image.image_role == "main" else "详情图"
                filename = (
                    f"{product}_{role_label}_{index_no}_{filename_timestamp(image.created_at)}.png"
                )
                zf.writestr(filename, _read_image_bytes(image))
                rows.append(
                    [
                        str(index_no),
                        filename,
                        "success",
                        str(image.width) if image.width is not None else "",
                        str(image.height) if image.height is not None else "",
                        to_iso(image.created_at) or "",
                        "",
                    ]
                )
            else:
                reason = (image.error_message if image is not None and image.error_message else "") or "生成失败"
                rows.append([str(index_no), "", "failed", "", "", "", reason])

        csv_buffer = io.StringIO()
        csv.writer(csv_buffer).writerows(rows)
        zf.writestr("manifest.csv", csv_buffer.getvalue().encode("utf-8-sig"))

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(zip_filename)}",
            "Cache-Control": "no-store",
        },
    )
