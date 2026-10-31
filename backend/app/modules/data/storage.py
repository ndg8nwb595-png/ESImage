"""单桶对象存储适配层（10 号 §3 / §6）。

默认 ``local`` 后端把 ``STORAGE_ROOT`` 当作桶根目录，目录结构与 MinIO 桶内前缀完全一致；
``minio`` 后端把同一套对象键映射到 MinIO 单桶。对象键只接受桶内相对路径，不生成公开 URL。

错误码：
- 50003：存储服务错误
- 30014：对象不存在或归档不可用
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error
from PIL import Image, UnidentifiedImageError

from app.modules.data.config import config

logger = logging.getLogger("esimage.storage")

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

    def local_path(self, key: str) -> Path:
        """返回本地绝对路径；仅供本地后端与兼容脚本使用。"""
        return self._absolute(key)

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


_NOT_FOUND_CODES = {"NoSuchKey", "NoSuchObject", "NoSuchVersion"}


def _http_datetime(value: str | None) -> datetime:
    """解析 HTTP 日期头；缺失或非法时退化为当前时间。"""
    if value:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc)


class MinioStorageAdapter:
    """MinIO 单桶实现；客户端惰性创建，构造阶段不访问网络。"""

    def __init__(
        self,
        client: Minio | None = None,
        *,
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        secure: bool | None = None,
        bucket: str | None = None,
    ) -> None:
        self.bucket = bucket or config.MINIO_BUCKET
        self.endpoint = config.MINIO_ENDPOINT if endpoint is None else endpoint
        self.access_key = config.MINIO_ACCESS_KEY if access_key is None else access_key
        self.secret_key = config.MINIO_SECRET_KEY if secret_key is None else secret_key
        self.secure = config.MINIO_SECURE if secure is None else secure
        self._client = client
        self._client_lock = threading.Lock()

    def _get_client(self) -> Minio:
        """首次使用时创建客户端，避免环境变量缺失导致模块导入失败。"""
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    if not self.endpoint:
                        raise StorageError(50003, "MinIO 未配置：缺少 MINIO_ENDPOINT")
                    self._client = Minio(
                        self.endpoint,
                        access_key=self.access_key,
                        secret_key=self.secret_key,
                        secure=self.secure,
                    )
        return self._client

    @staticmethod
    def _is_not_found(exc: S3Error) -> bool:
        return exc.code in _NOT_FOUND_CODES

    def _raise_io_error(self, action: str, key: str, exc: Exception) -> None:
        """把 SDK 异常统一映射为 50003，并避免把密钥写入日志。"""
        logger.error("MinIO %s失败 key=%s reason=%s", action, key, exc)
        raise StorageError(50003, f"{action}失败：{key}") from exc

    @staticmethod
    def _close_response(response) -> None:
        """释放 HTTP 连接：close 后再显式归还连接池。"""
        try:
            response.close()
        finally:
            release = getattr(response, "release_conn", None)
            if callable(release):
                release()

    def put_object(self, key: str, content: bytes, mime: str | None = None) -> ObjectInfo:
        key = validate_object_key(key)
        # 直接使用调用方传入的 bytes，避免大图写入前多复制一份
        payload = content
        content_type = mime or self._guess_mime(key) or "application/octet-stream"
        try:
            result = self._get_client().put_object(
                self.bucket,
                key,
                BytesIO(payload),
                len(payload),
                content_type=content_type,
            )
        except S3Error as exc:
            self._raise_io_error("写入对象", key, exc)
        except Exception as exc:  # 网络错误等非 S3Error 也按 50003 处理
            self._raise_io_error("写入对象", key, exc)
        etag = str(getattr(result, "etag", "") or "").strip('"')
        return ObjectInfo(key, len(payload), etag, mime, datetime.now(timezone.utc))

    def get_object(self, key: str) -> tuple[bytes, ObjectInfo]:
        key = validate_object_key(key)
        try:
            response = self._get_client().get_object(self.bucket, key)
        except S3Error as exc:
            if self._is_not_found(exc):
                raise ObjectNotFound(key) from exc
            self._raise_io_error("读取对象", key, exc)
        except Exception as exc:
            self._raise_io_error("读取对象", key, exc)
        try:
            content = response.read()
            headers = getattr(response, "headers", None) or {}
        except Exception as exc:
            self._raise_io_error("读取对象", key, exc)
        finally:
            self._close_response(response)
        etag = str(headers.get("ETag", "") or "").strip('"')
        return content, ObjectInfo(
            key,
            len(content),
            etag,
            headers.get("Content-Type"),
            _http_datetime(headers.get("Last-Modified")),
        )

    def open_object(self, key: str) -> BinaryIO:
        """返回 MinIO 响应流；调用方负责 close/release_conn。"""
        key = validate_object_key(key)
        try:
            return self._get_client().get_object(self.bucket, key)
        except S3Error as exc:
            if self._is_not_found(exc):
                raise ObjectNotFound(key) from exc
            self._raise_io_error("打开对象", key, exc)
        except Exception as exc:
            self._raise_io_error("打开对象", key, exc)

    def stat_object(self, key: str) -> ObjectInfo | None:
        key = validate_object_key(key)
        try:
            stat = self._get_client().stat_object(self.bucket, key)
        except S3Error as exc:
            if self._is_not_found(exc):
                return None
            self._raise_io_error("读取对象元数据", key, exc)
        except Exception as exc:
            self._raise_io_error("读取对象元数据", key, exc)
        return ObjectInfo(
            key,
            stat.size,
            str(stat.etag or "").strip('"'),
            stat.content_type,
            stat.last_modified or datetime.now(timezone.utc),
        )

    def exists(self, key: str | None) -> bool:
        if not key:
            return False
        return self.stat_object(key) is not None

    def copy_object(self, src: str, dst: str) -> ObjectInfo:
        src = validate_object_key(src)
        dst = validate_object_key(dst)
        try:
            self._get_client().copy_object(
                self.bucket,
                dst,
                CopySource(self.bucket, src),
            )
        except S3Error as exc:
            if self._is_not_found(exc):
                raise ObjectNotFound(src) from exc
            self._raise_io_error("复制对象", src, exc)
        except Exception as exc:
            self._raise_io_error("复制对象", src, exc)
        return self.stat_object(dst) or ObjectInfo(
            dst, 0, "", None, datetime.now(timezone.utc)
        )

    def delete_object(self, key: str) -> None:
        """删除对象；MinIO remove_object 本身幂等。"""
        key = validate_object_key(key)
        try:
            self._get_client().remove_object(self.bucket, key)
        except Exception as exc:
            self._raise_io_error("删除对象", key, exc)

    def path(self, key: str) -> Path:
        """MinIO 后端没有本地路径，显式拒绝以免调用方误用。"""
        raise StorageError(50003, f"MinIO 后端不支持本地路径：{key}")

    @staticmethod
    def _guess_mime(key: str) -> str | None:
        ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
        return _ALLOWED_FORMATS.get(ext)


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
