"""统一对象存储门面。

业务文件（上传图、生成图、缩略图、归档件）统一通过本门面读写：
- ``STORAGE_BACKEND=local``：落在 ``STORAGE_ROOT`` 目录，保持原有本地行为；
- ``STORAGE_BACKEND=minio``：落在 MinIO 单桶 ``esimage``，对象键与本地目录一致。

本地后端保留 ``path()`` 供脚本与兼容代码使用；MinIO 后端不暴露本地路径。
"""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from app.modules.data.storage import (
    LocalStorageAdapter,
    ObjectInfo,
    ObjectNotFound,
    StorageError,
    get_storage,
)


class Storage:
    """按配置委托给本地或 MinIO 适配器。"""

    def __init__(self, backend=None) -> None:
        # 允许测试注入后端，生产路径仍由 get_storage() 按环境变量选择
        self._backend = backend if backend is not None else get_storage()

    @property
    def is_local(self) -> bool:
        return isinstance(self._backend, LocalStorageAdapter)

    def save(self, relative_path: str, data: bytes) -> ObjectInfo:
        """写入对象，自动创建父目录（本地）或桶内前缀（MinIO）。"""
        return self._backend.put_object(relative_path, data)

    def read_bytes(self, relative_path: str) -> bytes:
        """读取完整对象内容；缺失抛 :class:`ObjectNotFound`。"""
        try:
            content, _ = self._backend.get_object(relative_path)
            return content
        except (ObjectNotFound, StorageError):
            raise
        except OSError as exc:
            # 本地磁盘错误统一归为存储服务错误，调用方只需处理 30014/50003
            raise StorageError(50003, f"读取对象失败：{relative_path}") from exc

    def open_stream(self, relative_path: str) -> BinaryIO:
        """返回可读流；调用方负责关闭。"""
        try:
            return self._backend.open_object(relative_path)
        except (ObjectNotFound, StorageError):
            raise
        except OSError as exc:
            raise StorageError(50003, f"打开对象失败：{relative_path}") from exc

    def path(self, relative_path: str) -> Path:
        """本地后端返回绝对路径；MinIO 后端显式拒绝。"""
        if not self.is_local:
            raise StorageError(50003, "MinIO 后端不支持本地路径")
        return self._backend.local_path(relative_path)

    def exists(self, relative_path: str | None) -> bool:
        if not relative_path:
            return False
        return self._backend.exists(relative_path)

    def delete(self, relative_path: str | None) -> None:
        """删除对象；不存在时静默忽略。"""
        if not relative_path:
            return
        self._backend.delete_object(relative_path)


storage = Storage()
