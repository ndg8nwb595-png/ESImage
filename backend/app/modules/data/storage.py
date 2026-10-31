"""单桶对象存储适配层（10 号 §3 / §6）。

默认 ``local`` 后端把 ``STORAGE_ROOT`` 当作桶根目录，目录结构与 MinIO 桶内前缀完全一致；
``minio`` 后端保留开关但不作为本 demo 验收项。对象键只接受桶内相对路径，不生成公开 URL。

错误码：
- 50003：存储服务错误
- 30014：对象不存在或归档不可用
"""

from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError

from app.modules.data.config import config

# 单文件上限 10MB（10,485,760 字节）
MAX_FILE_SIZE = 10 * 1024 * 1024
# 缩略图最大宽度
THUMBNAIL_MAX_WIDTH = 400
THUMBNAIL_QUALITY = 80
# Pillow 解压炸弹阈值（业务层还会对宽高乘积显式校验）
MAX_IMAGE_PIXELS = 40_000_000

_ALLOWED_FORMATS = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


class StorageError(Exception):
    """存储层业务异常。"""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ObjectNotFound(StorageError):
    """对象不存在或归档不可用，映射为 30014。"""

    def __init__(self, key: str) -> None:
        super().__init__(30014, "文件归档中，请稍后重试")
        self.key = key


@dataclass
class ObjectInfo:
    """对象元数据。"""

    key: str
    size: int
    etag: str
    mime: str | None
    updated_at: datetime


def _md5(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def validate_object_key(key: str) -> str:
    """校验对象键：非空、无前导 ``/``、无 ``..``、无控制字符、无反斜杠。"""
    if not key:
        raise StorageError(50003, "对象键为空")
    if key.startswith("/") or "\\" in key:
        raise StorageError(50003, f"非法对象键：{key}")
    if ".." in key.split("/"):
        raise StorageError(50003, f"非法对象键：{key}")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in key):
        raise StorageError(50003, f"非法对象键：{key}")
    return key


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _ext_from_mime(mime: str) -> str:
    return next((ext for ext, m in _ALLOWED_FORMATS.items() if m == mime), "")


def upload_path(user_id: int, session_id: int | None, ext: str) -> str:
    """上传图原件路径；未绑定会话时落在 ``unbound/`` 段。"""
    name = f"{_new_uuid()}.{ext}"
    if session_id is None:
        return f"uploads/{user_id}/unbound/{name}"
    return f"uploads/{user_id}/{session_id}/{name}"


def upload_thumbnail_path(user_id: int, session_id: int | None, object_uuid: str) -> str:
    """上传图缩略图路径（省略批次段，见接口文档 §8）。"""
    name = f"{object_uuid}_thumb.webp"
    if session_id is None:
        return f"thumbnails/{user_id}/unbound/{name}"
    return f"thumbnails/{user_id}/{session_id}/{name}"


def generated_path(user_id: int, session_id: int, batch_id: int) -> str:
    return f"generated/{user_id}/{session_id}/{batch_id}/{_new_uuid()}.png"


def generated_thumbnail_path(user_id: int, session_id: int, batch_id: int, object_uuid: str) -> str:
    return f"thumbnails/{user_id}/{session_id}/{batch_id}/{object_uuid}_thumb.webp"


def archive_key(key: str) -> str:
    """归档对象键：``archive/{原相对路径}``。"""
    return f"archive/{validate_object_key(key)}"


def object_uuid_from_path(key: str, stem_suffix: str = "") -> str:
    """从对象路径提取 UUID（文件名部分），用于拼接缩略图路径。"""
    name = key.rsplit("/", 1)[-1]
    if stem_suffix and name.endswith(stem_suffix):
        name = name[: -len(stem_suffix)]
    return name.rsplit(".", 1)[0]


class LocalStorageAdapter:
    """本地目录实现的存储适配器。"""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root if root is not None else config.STORAGE_ROOT).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _absolute(self, key: str) -> Path:
        target = (self.root / validate_object_key(key)).resolve()
        if self.root not in target.parents and target != self.root:
            raise StorageError(50003, f"非法对象键：{key}")
        return target

    def put_object(self, key: str, content: bytes, mime: str | None = None) -> ObjectInfo:
        target = self._absolute(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return ObjectInfo(key, len(content), _md5(content), mime, datetime.now(timezone.utc))

    def get_object(self, key: str) -> tuple[bytes, ObjectInfo]:
        target = self._absolute(key)
        if not target.is_file():
            raise ObjectNotFound(key)
        content = target.read_bytes()
        return content, ObjectInfo(
            key, len(content), _md5(content), self._guess_mime(key), datetime.now(timezone.utc)
        )

    def open_object(self, key: str) -> BinaryIO:
        """返回可读二进制流；对象不存在抛出 :class:`ObjectNotFound`。"""
        target = self._absolute(key)
        if not target.is_file():
            raise ObjectNotFound(key)
        return target.open("rb")

    def stat_object(self, key: str) -> ObjectInfo | None:
        target = self._absolute(key)
        if not target.is_file():
            return None
        stat = target.stat()
        return ObjectInfo(
            key, stat.st_size, "", self._guess_mime(key), datetime.fromtimestamp(
                stat.st_mtime, tz=timezone.utc
            )
        )

    def exists(self, key: str | None) -> bool:
        if not key:
            return False
        return self._absolute(key).is_file()

    def copy_object(self, src: str, dst: str) -> ObjectInfo:
        source = self._absolute(src)
        if not source.is_file():
            raise ObjectNotFound(src)
        target = self._absolute(dst)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return self.stat_object(dst) or ObjectInfo(dst, 0, "", None, datetime.now(timezone.utc))

    def delete_object(self, key: str) -> None:
        """删除对象；对象已不存在时视为成功（归档幂等重试）。"""
        target = self._absolute(key)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError(50003, f"删除对象失败：{key}") from exc

    @staticmethod
    def _guess_mime(key: str) -> str | None:
        ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
        return _ALLOWED_FORMATS.get(ext)


class MinioStorageAdapter(LocalStorageAdapter):
    """MinIO 后端占位：本 demo 不验收。"""

    def __init__(self) -> None:  # pragma: no cover - 非本 demo 范围
        raise NotImplementedError("MinIO 后端不在本 demo 验收范围内，请使用 STORAGE_BACKEND=local")


def get_storage():
    """按配置返回存储适配器。"""
    if config.STORAGE_BACKEND == "minio":
        return MinioStorageAdapter()
    if config.STORAGE_BACKEND != "local":
        raise StorageError(50003, f"不支持的存储后端：{config.STORAGE_BACKEND}")
    return LocalStorageAdapter()


# ---- 上传校验与缩略图 ----

def validate_upload(filename: str, mime: str, content: bytes) -> dict:
    """校验上传图片：格式、MIME 与扩展名一致、大小、可解码、宽高可读。

    返回 ``{"ext": "png", "width": ..., "height": ...}``；不满足时抛 :class:`StorageError`
    且不落库、不落对象。
    """
    if len(content) > MAX_FILE_SIZE:
        raise StorageError(30006, "文件大小不能超过 10MB")

    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in _ALLOWED_FORMATS:
        raise StorageError(30006, "仅支持 JPG、PNG、WEBP 格式")
    if _ALLOWED_FORMATS[ext] != mime.lower():
        raise StorageError(30006, "文件扩展名与 MIME 类型不符")

    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise StorageError(30006, "图片尺寸过大")
            image.load()
            width, height = image.width, image.height
    except StorageError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Exception):  # noqa: BLE001
        raise StorageError(30006, "图片文件损坏，无法解码") from None

    return {"ext": ext, "width": width, "height": height}


def make_thumbnail(content: bytes) -> bytes:
    """生成最大宽度 400px、WebP、质量 80 的缩略图；原图宽度不超过 400px 时不放大。"""
    try:
        with Image.open(BytesIO(content)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise StorageError(50003, "图片尺寸过大")
            image.load()
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGB")
            if image.width > THUMBNAIL_MAX_WIDTH:
                ratio = THUMBNAIL_MAX_WIDTH / float(image.width)
                image = image.resize(
                    (THUMBNAIL_MAX_WIDTH, max(1, int(image.height * ratio)))
                )
            buffer = BytesIO()
            image.save(buffer, format="WEBP", quality=THUMBNAIL_QUALITY, method=4)
            return buffer.getvalue()
    except StorageError:
        raise
    except Exception:  # noqa: BLE001
        raise StorageError(50003, "缩略图生成失败") from None
