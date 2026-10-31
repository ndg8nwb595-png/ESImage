"""生图任务公共校验、权限、幂等与序列化工具。"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.common import (
    filename_timestamp,
    get_owned_session,
    image_content_url,
    image_thumbnail_url,
    now_utc,
    require_permission,
    safe_filename_part,
    session_title_from_product,
    to_iso,
    validate_idempotency_key,
    validate_product_name,
    validate_style_text,
)
from app.core.response import ApiError
from app.models.config import Template
from app.models.workspace import ChatMessage, GeneratedImage, GenerationBatch, UploadedAsset

MAX_UPLOAD_COUNT = 5
# 接口文档 demo 约定：512~2048 且为 8 的倍数
MIN_IMAGE_DIMENSION = 512
MAX_IMAGE_DIMENSION = 2048
# 2 号 demo 的既有上限，超出仍按 10004 返回，保持错误码兼容
LEGACY_MAX_IMAGE_DIMENSION = 4096
IMAGE_DIMENSION_STEP = 8
DEFAULT_IMAGE_DIMENSION = 1000

FULL_IMAGE_COUNT = 6

# 单实例最小 demo 的进程内锁：覆盖创建批次、确认、取消、单张重试的 check-then-act
_GENERATION_LOCK = threading.RLock()


@contextmanager
def generation_lock():
    """串行化需要先查后写的生成任务操作。"""
    with _GENERATION_LOCK:
        yield





def validate_size(width: int | None, height: int | None) -> tuple[int, int]:
    """宽高：省略或 null 时默认 1000；否则 512~2048 且为 8 的倍数。"""
    final_width = DEFAULT_IMAGE_DIMENSION if width is None else width
    final_height = DEFAULT_IMAGE_DIMENSION if height is None else height
    for value in (final_width, final_height):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ApiError(400, 10003, "宽高需为 512~2048 的正整数且为 8 的倍数")
        # 保持 2 号 demo 的既有错误码：超过 4096 仍返回 10004
        if value > LEGACY_MAX_IMAGE_DIMENSION:
            raise ApiError(400, 10004, "宽高超出范围")
        if (
            value < MIN_IMAGE_DIMENSION
            or value > MAX_IMAGE_DIMENSION
            or value % IMAGE_DIMENSION_STEP != 0
        ):
            raise ApiError(400, 10003, "宽高需为 512~2048 的正整数且为 8 的倍数")
    return final_width, final_height



def get_active_template(db: Session, template_id: int | None) -> Template | None:
    """模板：null 表示不使用；非 null 必须是启用中的模板。"""
    if template_id is None:
        return None
    template = db.get(Template, template_id)
    if template is None or template.status != "active":
        raise ApiError(404, 30016, "模板/素材/尺寸不存在")
    return template



def validate_uploads(
    db: Session,
    user_id: int,
    upload_ids: list[int] | None,
    target_session_id: int | None,
) -> list[UploadedAsset]:
    """校验上传图归属、状态、数量与绑定会话，并按提交顺序返回。"""
    if not upload_ids:
        return []
    if len(upload_ids) > MAX_UPLOAD_COUNT or len(set(upload_ids)) != len(upload_ids):
        raise ApiError(400, 30006, "上传文件不符合要求")

    assets = list(db.scalars(select(UploadedAsset).where(UploadedAsset.id.in_(upload_ids))))
    assets_by_id = {asset.id: asset for asset in assets}
    ordered: list[UploadedAsset] = []
    for upload_id in upload_ids:
        asset = assets_by_id.get(upload_id)
        if asset is None or asset.user_id != user_id or asset.status != "active":
            raise ApiError(400, 30006, "上传文件不符合要求")
        if asset.session_id is not None and asset.session_id != target_session_id:
            raise ApiError(400, 30006, "上传文件不符合要求")
        ordered.append(asset)
    return ordered


def running_batch_count(db: Session, user_id: int, *, exclude_batch_id: int | None = None) -> int:
    """当前用户 queued/running 批次数；sample_ready 不计入。"""
    stmt = (
        select(func.count())
        .select_from(GenerationBatch)
        .where(
            GenerationBatch.user_id == user_id,
            GenerationBatch.status.in_(("queued", "running")),
        )
    )
    if exclude_batch_id is not None:
        stmt = stmt.where(GenerationBatch.id != exclude_batch_id)
    return int(db.scalar(stmt) or 0)


def latest_confirmable_sample_id(db: Session, user_id: int) -> int | None:
    """当前用户最近创建、仍为 sample_ready 的示例批次 ID。"""
    return db.scalar(
        select(GenerationBatch.id)
        .where(
            GenerationBatch.user_id == user_id,
            GenerationBatch.batch_type == "sample",
            GenerationBatch.status == "sample_ready",
        )
        .order_by(GenerationBatch.created_at.desc(), GenerationBatch.id.desc())
        .limit(1)
    )


def get_owned_batch(db: Session, user_id: int, batch_id: int) -> GenerationBatch:
    batch = db.get(GenerationBatch, batch_id)
    if batch is None or batch.user_id != user_id:
        raise ApiError(404, 30004, "批次不存在")
    return batch


def get_owned_image(db: Session, user_id: int, image_id: int) -> GeneratedImage:
    image = db.get(GeneratedImage, image_id)
    if image is None or image.user_id != user_id:
        raise ApiError(404, 30014, "文件不存在")
    return image


def current_images(db: Session, batch_id: int) -> list[GeneratedImage]:
    """返回每个 index 的最新尝试（superseded 不返回），按 index 升序。"""
    rows = list(
        db.scalars(
            select(GeneratedImage)
            .where(
                GeneratedImage.batch_id == batch_id,
                GeneratedImage.status != "superseded",
            )
            .order_by(GeneratedImage.index_no.asc(), GeneratedImage.attempt_no.desc())
        )
    )
    latest: dict[int, GeneratedImage] = {}
    for image in rows:
        latest.setdefault(image.index_no, image)
    return [latest[index] for index in sorted(latest)]




def template_thumbnail_url(template_id: int) -> str:
    return f"/api/v1/templates/{template_id}/thumbnail"


def image_payload(image: GeneratedImage, batch: GenerationBatch) -> dict[str, Any]:
    """公开图片字段；4 号 demo 在 2 号字段上增加类型/尝试号/历史可见性。"""
    has_file = bool(image.file_path)
    has_thumbnail = bool(image.thumbnail_path)
    return {
        "image_id": image.id,
        "index": image.index_no,
        "image_role": image.image_role,
        "image_type": image.image_type,
        "attempt_no": image.attempt_no,
        "status": image.status,
        "thumbnail_url": image_thumbnail_url(image.id) if has_thumbnail else None,
        "content_url": image_content_url(image.id) if has_file else None,
        "error_message": image.error_message,
        "width": image.width if image.width is not None else batch.width,
        "height": image.height if image.height is not None else batch.height,
        "is_history_visible": image.is_history_visible,
    }


def batch_payload(db: Session, batch: GenerationBatch) -> dict[str, Any]:
    """批次详情；images 只返回每个 index 的最新尝试。"""
    return {
        "batch_id": batch.id,
        "batch_type": batch.batch_type,
        "source_sample_batch_id": batch.source_sample_batch_id,
        "status": batch.status,
        "stage": batch.stage,
        "total_count": batch.total_count,
        "completed_count": batch.completed_count,
        "images": [image_payload(image, batch) for image in current_images(db, batch.id)],
        "error_message": batch.error_message,
        "created_at": to_iso(batch.created_at),
        "finished_at": to_iso(batch.finished_at),
    }







def image_role_label(image: GeneratedImage) -> str:
    return "主图" if image.image_role == "main" else "详情图"


def image_download_filename(batch: GenerationBatch, image: GeneratedImage) -> str:
    return (
        f"{safe_filename_part(batch.product_name)}_{image_role_label(image)}_"
        f"{image.index_no}_{filename_timestamp(image.created_at)}.png"
    )


def build_params_snapshot(
    *,
    product_name: str,
    style_text: str | None,
    width: int,
    height: int,
    template: Template | None,
    upload_ids: list[int],
    requirement_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    """创建批次时固化的参数快照；后续模板修改不影响历史批次。"""
    return {
        "product_name": product_name,
        "style_text": style_text,
        "width": width,
        "height": height,
        "template_id": template.id if template else None,
        "template_name": template.name if template else None,
        "template_prompt": template.prompt_template if template else None,
        "template_layout_ref": template.layout_ref if template else None,
        "upload_ids": upload_ids,
        "image_composition": "1 main + 5 detail",
        "requirement_summary": requirement_summary,
        "created_at": to_iso(now_utc()),
    }


def chat_summary(db: Session, session_id: int | None, rounds: int = 10) -> str:
    """最近 N 轮聊天摘要；用消息原文拼接，避免额外调用模型。"""
    if session_id is None:
        return ""
    rows = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(rounds * 2)
        )
    )
    rows.reverse()
    lines = []
    for message in rows:
        content = (message.content or "").strip().replace("\n", " ")
        if len(content) > 200:
            content = content[:200] + "…"
        lines.append(f"{message.role}: {content}")
    return "\n".join(lines)
