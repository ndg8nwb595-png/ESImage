"""本地文件存储适配层。

最小 demo 用本地目录替代 MinIO，并简化了 10 号文档 §6.2 的路径层级：
- 上传原图：uploads/{user_id}/{uuid}.{ext}
- 生成原图：generated/{user_id}/{uuid}.png
- 缩略图：thumbnails/{user_id}/{uuid}.webp

UUID 保证文件名不冲突；正式实现切换到 MinIO 时再按文档补 session_id / batch_id 层级。
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings


class LocalStorage:
    """限定在 STORAGE_ROOT 内的本地文件存储。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or settings.STORAGE_ROOT).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _absolute(self, relative_path: str) -> Path:
        """拼接绝对路径，并阻止路径穿越到存储根目录之外。"""
        target = (self.root / relative_path).resolve()
        if self.root not in target.parents and target != self.root:
            raise ValueError(f"非法的存储路径：{relative_path}")
        return target

    def save(self, relative_path: str, data: bytes) -> Path:
        """写入文件，自动创建父目录。"""
        target = self._absolute(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def path(self, relative_path: str) -> Path:
        """返回绝对路径；文件不存在时由调用方处理。"""
        return self._absolute(relative_path)

    def exists(self, relative_path: str | None) -> bool:
        return bool(relative_path) and self._absolute(relative_path).is_file()

    def delete(self, relative_path: str | None) -> None:
        """删除文件；不存在时静默忽略。"""
        if not relative_path:
            return
        try:
            self._absolute(relative_path).unlink(missing_ok=True)
        except ValueError:
            return


storage = LocalStorage()
