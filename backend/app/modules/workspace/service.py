"""创作工作台公共校验与序列化工具。"""

from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.core.deps import require_permission  # 重新导出，供 workspace 各子路由复用
from app.core.response import ApiError
from app.models.workspace import CreativeSession

MAX_UPLOAD_COUNT = 5
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# 演示管线按请求宽高创建真彩色位图，必须限制尺寸，避免 OOM
MAX_IMAGE_DIMENSION = 4096
# 上传图片解码后的像素上限（约 4000 万像素）
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}

MIME_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# 单实例最小 demo 的进程内锁：覆盖聊天幂等、批次并发、上传数量与确认全套。
# 正式实现应替换为 Redis 幂等键 + 数据库唯一约束/行锁。
_WORKSPACE_LOCK = threading.RLock()


@contextmanager
def workspace_lock():
    """串行化需要 check-then-act 的工作台写操作。"""
    with _WORKSPACE_LOCK:
        yield


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
    """宽高：省略或 null 时默认 1000；否则必须为正整数且不超过演示管线上限。"""
    final_width = 1000 if width is None else width
    final_height = 1000 if height is None else height
    if (
        not isinstance(final_width, int)
        or isinstance(final_width, bool)
        or not isinstance(final_height, int)
        or isinstance(final_height, bool)
        or final_width <= 0
        or final_height <= 0
    ):
        raise ApiError(400, 10003, "宽高需为正整数")
    if final_width > MAX_IMAGE_DIMENSION or final_height > MAX_IMAGE_DIMENSION:
        raise ApiError(400, 10004, "宽高超出范围")
    return final_width, final_height


def validate_template_id(template_id: int | None) -> None:
    """最小 demo 不支持模板，非 null 一律 30016。"""
    if template_id is not None:
        raise ApiError(404, 30016, "模板/素材/尺寸不存在")


def validate_message_content(value: str | None) -> str:
    """消息正文：去首尾空格后 1~2000 字符。"""
    if value is None or value.strip() == "":
        raise ApiError(400, 10002, "请输入内容")
    content = value.strip()
    if len(content) > 2000:
        raise ApiError(400, 10004, "消息不能超过 2000 个字符")
    return content


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


def get_owned_session(db, user_id: int, session_id: int, *, allow_hidden: bool = False) -> CreativeSession:
    """读取当前用户的会话；不存在、已隐藏或不属于当前用户统一 30013。"""
    session = db.get(CreativeSession, session_id)
    if session is None or session.user_id != user_id:
        raise ApiError(404, 30013, "会话不存在")
    if session.status != "active" and not allow_hidden:
        raise ApiError(404, 30013, "会话不存在")
    return session


def session_title_from_message(content: str) -> str:
    """首条消息建会话：取消息前 20 个字符。"""
    title = content.strip()[:20]
    return title or "未命名会话"


def session_title_from_product(product_name: str) -> str:
    """首次生成建会话：取商品名称，最多 50 字符。"""
    title = product_name.strip()[:50]
    return title or "未命名会话"


def empty_requirement_summary(product_name: str) -> dict[str, Any]:
    """最小需求摘要结构。"""
    return {
        "product_name": product_name,
        "category": None,
        "selling_points": [],
        "target_audience": None,
        "scenes": [],
        "tone": None,
        "constraints": [],
    }


def merge_requirement_summary(
    existing: dict[str, Any] | None, product_name: str
) -> dict[str, Any]:
    """保留已有摘要字段，只更新商品名称。"""
    summary = dict(existing) if existing else empty_requirement_summary(product_name)
    summary["product_name"] = product_name
    summary.setdefault("category", None)
    summary.setdefault("selling_points", [])
    summary.setdefault("target_audience", None)
    summary.setdefault("scenes", [])
    summary.setdefault("tone", None)
    summary.setdefault("constraints", [])
    return summary


def to_iso(value: datetime | None) -> str | None:
    """统一输出东八区 ISO 8601；数据库返回 UTC 时自动转换。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(settings.TZ).isoformat()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def upload_file_url(upload_id: int) -> str:
    return f"/api/v1/uploads/{upload_id}/content"


def upload_thumbnail_url(upload_id: int) -> str:
    return f"/api/v1/uploads/{upload_id}/thumbnail"


def image_content_url(image_id: int) -> str:
    return f"/api/v1/images/{image_id}/content"


def image_thumbnail_url(image_id: int) -> str:
    return f"/api/v1/images/{image_id}/thumbnail"


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
