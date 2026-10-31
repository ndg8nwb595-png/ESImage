"""创作工作台公共校验与序列化工具。"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi.responses import FileResponse, Response

from app.core.config import settings
from app.core.deps import (  # 重新导出，供 workspace/history 子路由复用
    require_any_permission,
    require_permission,
)
from app.core.response import ApiError
from app.models.workspace import CreativeSession, GeneratedImage
from app.modules.data.storage import ObjectNotFound, StorageError
from app.modules.workspace.storage import storage

logger = logging.getLogger("esimage.storage")

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
    """把文件名非法字符替换为下划线。

    规则见 5 号接口文档 §8.3：`/ \\ : * ? " < > |`、控制字符（0x00~0x1F）
    以及结尾的点与空格统一替换为下划线。
    """
    invalid = set('\\/:*?"<>|')
    chars = ["_" if ch in invalid or ord(ch) < 0x20 else ch for ch in value]
    # 结尾的点与空格逐个替换，避免 Windows 无法保存或截断扩展名
    position = len(chars) - 1
    while position >= 0 and chars[position] in (" ", "."):
        chars[position] = "_"
        position -= 1
    cleaned = "".join(chars)
    return cleaned or "未命名商品"


def image_download_filename(
    product_name: str,
    image_role: str,
    index_no: int,
    created_at: datetime | None,
) -> str:
    """单张与 ZIP 内图片共用同一命名规则。"""
    role_label = "主图" if image_role == "main" else "详情图"
    return (
        f"{safe_filename_part(product_name)}_{role_label}_"
        f"{index_no}_{filename_timestamp(created_at)}.png"
    )


def archive_relative_path(image: GeneratedImage) -> str:
    """归档原件的相对路径；调用方需先确认 archived_at 非空。"""
    return f"archive/{image.file_path}"


def _log_archive_error(image: GeneratedImage, path: str, reason: str) -> None:
    """记录归档读取错误，不包含 token 等敏感信息。"""
    logger.error(
        "归档读取失败 image_id=%s batch_id=%s archive_path=%s reason=%s",
        image.id,
        image.batch_id,
        path,
        reason,
    )


def read_media_bytes(relative_path: str, *, missing_message: str = "文件不存在") -> bytes:
    """读取热存储对象：缺失返回 404/30014，存储异常返回 500/50003。

    同时适用于本地目录与 MinIO 后端；调用方无需关心后端类型。
    """
    try:
        return storage.read_bytes(relative_path)
    except ObjectNotFound:
        raise ApiError(404, 30014, missing_message) from None
    except StorageError as exc:
        logger.error("存储读取失败 path=%s reason=%s", relative_path, exc.message)
        raise ApiError(500, 50003, "存储服务错误") from exc


def media_response(
    relative_path: str,
    *,
    media_type: str,
    headers: dict[str, str],
    missing_message: str = "文件不存在",
) -> Response:
    """构造媒体响应：本地后端保留 FileResponse 的缓存头与 Range 支持。

    MinIO 后端没有本地文件，读取完整对象后返回缓冲 Response。
    """
    if storage.is_local:
        path = storage.path(relative_path)
        if not path.is_file():
            raise ApiError(404, 30014, missing_message)
        return FileResponse(path, media_type=media_type, headers=headers)
    return Response(
        content=read_media_bytes(relative_path, missing_message=missing_message),
        media_type=media_type,
        headers=headers,
    )


def read_image_bytes(image: GeneratedImage) -> bytes:
    """读取生成图原件；归档件从 `archive/{file_path}` 读取并受超时约束。

    - 热数据缺失：404 `30014`「文件不存在」
    - 归档件缺失/超时/存储异常：404 `30014`「文件归档中，请稍后重试」
    """
    if not image.file_path:
        raise ApiError(404, 30014, "文件不存在")

    if image.archived_at is None:
        try:
            return storage.read_bytes(image.file_path)
        except ObjectNotFound:
            raise ApiError(404, 30014, "文件不存在") from None
        except StorageError as exc:
            logger.error(
                "热存储读取失败 image_id=%s batch_id=%s path=%s reason=%s",
                image.id,
                image.batch_id,
                image.file_path,
                exc.message,
            )
            raise ApiError(500, 50003, "存储服务错误") from exc

    relative_path = archive_relative_path(image)

    # 本地文件/对象存储读取本身没有超时参数，用线程池模拟部署配置的读取超时。
    # 注意不要用 with 语句：它会在退出时等待线程，导致超时失效。
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(storage.read_bytes, relative_path)
        try:
            return future.result(timeout=settings.ARCHIVE_READ_TIMEOUT_SECONDS)
        except ObjectNotFound:
            _log_archive_error(image, relative_path, "file_missing")
            raise ApiError(404, 30014, "文件归档中，请稍后重试") from None
        except FutureTimeoutError:
            _log_archive_error(image, relative_path, "timeout")
            raise ApiError(404, 30014, "文件归档中，请稍后重试") from None
        except StorageError as exc:
            _log_archive_error(image, relative_path, f"storage_error: {exc.message}")
            raise ApiError(404, 30014, "文件归档中，请稍后重试") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
