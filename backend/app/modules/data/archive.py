"""5 年归档任务与归档读取（10 号 §7 / 接口文档 §5）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workspace import GeneratedImage, UploadedAsset
from app.modules.data.config import config
from app.modules.data.db import SessionLocal
from app.modules.data.storage import (
    LocalStorageAdapter,
    ObjectNotFound,
    StorageError,
    archive_key,
    get_storage,
)

TZ_SHANGHAI = timezone(timedelta(hours=8))


def parse_now(value: str | None) -> datetime:
    """解析 ``--now``；缺省取当前时间（Asia/Shanghai）。"""
    if value is None:
        return datetime.now(TZ_SHANGHAI)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TZ_SHANGHAI)
    return parsed.astimezone(TZ_SHANGHAI)


@dataclass
class ArchiveFailure:
    table: str
    record_id: int
    object_key: str
    reason: str


@dataclass
class ArchiveReport:
    scanned: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    duration_ms: int = 0
    failures: list[ArchiveFailure] = field(default_factory=list)


def _archive_one(
    storage: LocalStorageAdapter,
    session: Session,
    table: str,
    record_id: int,
    key: str,
    now: datetime,
) -> None:
    """单条归档：复制 -> 校验 -> 删除原件 -> 回写 archived_at。

    任一步失败抛 :class:`StorageError`，保持 archived_at 为空且不删除原件。
    """
    target = archive_key(key)

    # 幂等：归档已存在且原件已不存在 -> 直接回写
    if storage.exists(target) and not storage.exists(key):
        _write_archived_at(session, table, record_id, now)
        return

    # 幂等：归档已存在且原件仍在 -> 校验后删除原件再回写
    if storage.exists(target) and storage.exists(key):
        original = storage.stat_object(key)
        archived = storage.stat_object(target)
        if original is None or archived is None or original.size != archived.size:
            raise StorageError(50003, "归档对象校验失败：大小不一致")
        storage.delete_object(key)
        _write_archived_at(session, table, record_id, now)
        return

    # 正常路径：原件存在，归档不存在
    if not storage.exists(key):
        raise StorageError(50003, "原件不存在，等待人工处理")
    storage.copy_object(key, target)
    original = storage.stat_object(key)
    archived = storage.stat_object(target)
    if original is None or archived is None or original.size != archived.size:
        raise StorageError(50003, "归档对象校验失败：大小不一致")
    storage.delete_object(key)
    _write_archived_at(session, table, record_id, now)


def _write_archived_at(session: Session, table: str, record_id: int, now: datetime) -> None:
    if table == "generated_images":
        record = session.get(GeneratedImage, record_id)
    else:
        record = session.get(UploadedAsset, record_id)
    if record is not None:
        record.archived_at = now
        session.commit()


def run_archive(now_value: str | None = None, retention_days: int | None = None) -> ArchiveReport:
    """执行一次归档，返回汇总报告。"""
    started = datetime.now(TZ_SHANGHAI)
    now = parse_now(now_value)
    days = retention_days if retention_days is not None else config.ARCHIVE_RETENTION_DAYS
    cutoff = now - timedelta(days=days)

    storage = get_storage()
    report = ArchiveReport()

    with SessionLocal() as session:
        images = session.scalars(
            select(GeneratedImage).where(
                GeneratedImage.created_at < cutoff,
                GeneratedImage.archived_at.is_(None),
                GeneratedImage.file_path.is_not(None),
            )
        ).all()
        uploads = session.scalars(
            select(UploadedAsset).where(
                UploadedAsset.created_at < cutoff,
                UploadedAsset.archived_at.is_(None),
                UploadedAsset.file_path.is_not(None),
            )
        ).all()

        report.scanned = len(images) + len(uploads)
        for table, records in (("generated_images", images), ("uploaded_assets", uploads)):
            for record in records:
                key = record.file_path
                if not key:
                    report.skipped += 1
                    continue
                try:
                    _archive_one(storage, session, table, record.id, key, now)
                    report.succeeded += 1
                except (StorageError, OSError) as exc:
                    report.failed += 1
                    reason = exc.message if isinstance(exc, StorageError) else str(exc)
                    report.failures.append(
                        ArchiveFailure(table, record.id, key, reason)
                    )

    report.duration_ms = int((datetime.now(TZ_SHANGHAI) - started).total_seconds() * 1000)
    return report


def read_object(file_path: str | None, archived_at: datetime | None) -> bytes:
    """按 ``archived_at`` 选择路径读取对象。

    - ``archived_at`` 为空：读原件 ``file_path``
    - 非空：读 ``archive/{file_path}``
    - 对象缺失或存储不可用：抛 :class:`ObjectNotFound`（30014），不回退读原件。
    """
    if not file_path:
        raise ObjectNotFound(file_path or "")
    storage = get_storage()
    key = archive_key(file_path) if archived_at is not None else file_path
    try:
        content, _ = storage.get_object(key)
        return content
    except ObjectNotFound:
        raise
    except StorageError as exc:
        if exc.code == 30014:
            raise ObjectNotFound(key) from exc
        raise
