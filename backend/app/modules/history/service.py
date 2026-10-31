"""历史作品查询、分页与序列化工具。

历史可见性口径对齐 5 号接口文档 §2.2：
批次属于当前用户、`batch_type=full`、状态 `completed`/`partially_failed`，
图片 `image_type=final`、`status=success`、`is_history_visible=true`。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.response import ApiError
from app.models.workspace import GeneratedImage, GenerationBatch
from app.modules.workspace.service import (
    image_content_url,
    image_thumbnail_url,
    to_iso,
)

# 历史页固定每页 20 条，不开放 page_size（5 号 §2.1 / 接口文档 §1.5）
HISTORY_PAGE_SIZE = 20
HISTORY_BATCH_STATUSES = ("completed", "partially_failed")


def visible_image_filters():
    """历史可见图片的公共过滤条件。"""
    return (
        GeneratedImage.image_type == "final",
        GeneratedImage.status == "success",
        GeneratedImage.is_history_visible.is_(True),
    )


def is_visible_image(image: GeneratedImage) -> bool:
    """判断单条图片记录是否满足历史可见口径。"""
    return (
        image.image_type == "final"
        and image.status == "success"
        and image.is_history_visible
    )


def parse_page(value: str | None) -> int:
    """解析 page：缺省 1，必须为正整数，否则 400 `10001`。"""
    if value is None or value == "":
        return 1
    try:
        page = int(value)
    except (TypeError, ValueError):
        raise ApiError(400, 10001, "页码参数错误") from None
    if page < 1:
        raise ApiError(400, 10001, "页码参数错误")
    return page


def _cover_images(db: Session, batch_ids: list[int]) -> dict[int, GeneratedImage]:
    """取每页批次的封面：序号最小的历史可见成功图。

    同一序号存在多次尝试时，取 `attempt_no` 最大、`id` 最大的记录。
    """
    if not batch_ids:
        return {}
    rows = db.scalars(
        select(GeneratedImage)
        .where(
            GeneratedImage.batch_id.in_(batch_ids),
            *visible_image_filters(),
        )
        .order_by(
            GeneratedImage.batch_id.asc(),
            GeneratedImage.index_no.asc(),
            GeneratedImage.attempt_no.desc(),
            GeneratedImage.id.desc(),
        )
    )
    covers: dict[int, GeneratedImage] = {}
    for image in rows:
        covers.setdefault(image.batch_id, image)
    return covers


def list_history(db: Session, user_id: int, page: int) -> dict[str, Any]:
    """分页查询当前用户的历史全套批次。"""
    offset = (page - 1) * HISTORY_PAGE_SIZE

    # 先按图片聚合出每个批次的历史可见成功张数，再连接批次表，避免 N+1。
    # 子查询内同时按 user_id 与批次条件收窄，避免每次请求聚合全站图片。
    visible_counts = (
        select(
            GeneratedImage.batch_id.label("batch_id"),
            func.count().label("success_count"),
        )
        .join(GenerationBatch, GenerationBatch.id == GeneratedImage.batch_id)
        .where(
            GeneratedImage.user_id == user_id,
            GenerationBatch.user_id == user_id,
            GenerationBatch.batch_type == "full",
            GenerationBatch.status.in_(HISTORY_BATCH_STATUSES),
            *visible_image_filters(),
        )
        .group_by(GeneratedImage.batch_id)
        .subquery()
    )
    base = (
        select(GenerationBatch, visible_counts.c.success_count)
        .join(visible_counts, visible_counts.c.batch_id == GenerationBatch.id)
        .where(
            GenerationBatch.user_id == user_id,
            GenerationBatch.batch_type == "full",
            GenerationBatch.status.in_(HISTORY_BATCH_STATUSES),
        )
    )

    total = int(
        db.scalar(select(func.count()).select_from(base.subquery())) or 0
    )
    # 页码超过总页数时直接返回空列表，避免超大 offset 溢出 PostgreSQL bigint
    if offset >= total:
        return {
            "items": [],
            "total": total,
            "page": page,
            "page_size": HISTORY_PAGE_SIZE,
        }

    rows = db.execute(
        base.order_by(
            GenerationBatch.created_at.desc(),
            GenerationBatch.id.desc(),
        )
        .offset(offset)
        .limit(HISTORY_PAGE_SIZE)
    ).all()

    covers = _cover_images(db, [batch.id for batch, _ in rows])
    items = []
    for batch, success_count in rows:
        cover = covers.get(batch.id)
        items.append(
            {
                "batch_id": batch.id,
                "product_name": batch.product_name,
                "main_count": 1,
                "detail_count": max(batch.total_count - 1, 0),
                "success_count": int(success_count),
                "total_count": batch.total_count,
                "cover_image_id": cover.id if cover else None,
                "cover_thumbnail_url": image_thumbnail_url(cover.id) if cover else None,
                "created_at": to_iso(batch.created_at),
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": HISTORY_PAGE_SIZE,
    }


def get_history_batch(db: Session, user_id: int, batch_id: int) -> GenerationBatch:
    """读取历史可见批次；不存在 404、越权 403、非历史范围 404。"""
    batch = db.get(GenerationBatch, batch_id)
    if batch is None:
        raise ApiError(404, 30004, "批次不存在")
    if batch.user_id != user_id:
        raise ApiError(403, 20005, "无权限")
    if batch.batch_type != "full" or batch.status not in HISTORY_BATCH_STATUSES:
        raise ApiError(404, 30004, "批次不存在")
    return batch


def visible_images(db: Session, batch_id: int) -> list[GeneratedImage]:
    """按序号升序返回批次的历史可见成功图；同序号只保留最新尝试。"""
    rows = db.scalars(
        select(GeneratedImage)
        .where(
            GeneratedImage.batch_id == batch_id,
            *visible_image_filters(),
        )
        .order_by(
            GeneratedImage.index_no.asc(),
            GeneratedImage.attempt_no.desc(),
            GeneratedImage.id.desc(),
        )
    )
    images: list[GeneratedImage] = []
    seen_indexes: set[int] = set()
    for image in rows:
        if image.index_no in seen_indexes:
            continue
        seen_indexes.add(image.index_no)
        images.append(image)
    return images


def detail_payload(batch: GenerationBatch, images: list[GeneratedImage]) -> dict[str, Any]:
    """批次详情响应；不返回提示词、模型与生成参数。"""
    return {
        "batch_id": batch.id,
        "product_name": batch.product_name,
        "style_text": batch.style_text,
        "width": batch.width,
        "height": batch.height,
        "main_count": 1,
        "detail_count": max(batch.total_count - 1, 0),
        "success_count": len(images),
        "total_count": batch.total_count,
        "status": batch.status,
        "created_at": to_iso(batch.created_at),
        "images": [
            {
                "image_id": image.id,
                "index": image.index_no,
                "image_role": image.image_role,
                "width": image.width,
                "height": image.height,
                "thumbnail_url": image_thumbnail_url(image.id),
                "content_url": image_content_url(image.id),
                "created_at": to_iso(image.created_at),
            }
            for image in images
        ],
    }
