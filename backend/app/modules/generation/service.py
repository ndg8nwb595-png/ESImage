"""生图任务公共校验、权限、幂等与序列化工具。"""

from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import AuthContext, get_current_auth
from app.core.response import ApiError
from app.models.config import Template
from app.models.workspace import (
    ChatMessage,
    CreativeSession,
    GeneratedImage,
    GenerationBatch,
    UploadedAsset,
)

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


def require_permission(code: str) -> Callable[..., AuthContext]:
    """生成权限校验依赖；缺少权限返回 403/20005。"""

    def dependency(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
        if code not in auth.permissions:
            raise ApiError(403, 20005, "无权限")
        return auth

    return dependency


def validate_product_name(value: str | None) -> str:
    """商品名称：去首尾空格后 1~60 字符。"""
    if value is None or value.strip() == "":
        raise ApiError(400, 10002, "请先填写商品名称")
    name = value.strip()
    if len(name) > 60:
        raise ApiError(400, 10004, "商品名称不能超过 60 个字符")
    return name


def validate_style_text(value: str | None) -> str | None:
    """风格：纯空格视为未填写；填写时 1~50 字符。"""
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    if len(text) > 50:
        raise ApiError(400, 10004, "风格不能超过 50 个字符")
    return text


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


def validate_idempotency_key(value: str | None, field_name: str) -> str:
    """幂等键：UUID，非空且不超过 64 字符。"""
    if value is None or value.strip() == "":
        raise ApiError(400, 10002, f"缺少{field_name}")
    key = value.strip()
    if len(key) > 64:
        raise ApiError(400, 10004, f"{field_name}不能超过 64 个字符")
    try:
        uuid.UUID(key)
    except (ValueError, AttributeError) as exc:
        raise ApiError(400, 10003, f"{field_name} 需为 UUID") from exc
    return key


def get_active_template(db: Session, template_id: int | None) -> Template | None:
    """模板：null 表示不使用；非 null 必须是启用中的模板。"""
    if template_id is None:
        return None
    template = db.get(Template, template_id)
    if template is None or template.status != "active":
        raise ApiError(404, 30016, "模板/素材/尺寸不存在")
    return template


def get_owned_session(
    db: Session, user_id: int, session_id: int, *, allow_hidden: bool = False
) -> CreativeSession:
    """读取当前用户的会话；不存在/已隐藏/非本人统一 30013。"""
    session = db.get(CreativeSession, session_id)
    if session is None or session.user_id != user_id:
        raise ApiError(404, 30013, "会话不存在")
    if session.status != "active" and not allow_hidden:
        raise ApiError(404, 30013, "会话不存在")
    return session


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


def image_content_url(image_id: int) -> str:
    return f"/api/v1/images/{image_id}/content"


def image_thumbnail_url(image_id: int) -> str:
    return f"/api/v1/images/{image_id}/thumbnail"


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


def session_title_from_product(product_name: str) -> str:
    title = product_name.strip()[:50]
    return title or "未命名会话"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    """统一输出东八区 ISO 8601；数据库返回 UTC 时自动转换。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(settings.TZ).isoformat()


def filename_timestamp(value: datetime | None) -> str:
    """文件名时间戳：东八区 yyyyMMddHHmmss。"""
    if value is None:
        value = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(settings.TZ).strftime("%Y%m%d%H%M%S")


def safe_filename_part(value: str) -> str:
    """把文件名非法字符替换为下划线。"""
    invalid = set('\\/:*?"<>|\r\n\t')
    cleaned = "".join("_" if ch in invalid else ch for ch in value).strip()
    return cleaned or "未命名商品"


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
