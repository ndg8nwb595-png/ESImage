"""生成批次与单图状态机。

只允许 PRD §3.3/§3.4/§3.5 与接口文档 §9 定义的状态迁移；
非法流转统一抛 IllegalTransition，由调用方转换为 30005 或记录失败。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.workspace import GeneratedImage, GenerationBatch


class IllegalTransition(RuntimeError):
    """非法的状态流转。"""


BATCH_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "cancelled", "failed"},
    "running": {"sample_ready", "completed", "partially_failed", "failed", "cancelled"},
    "sample_ready": {"confirmed", "cancelled"},
    "confirmed": set(),
    # 单张重生成失败时允许 completed -> partially_failed / failed（接口文档 §9.4）
    "completed": {"partially_failed", "failed"},
    # 单张重试成功后允许回到 completed；全部失败时 failed
    "partially_failed": {"completed", "failed"},
    "failed": set(),
    "cancelled": set(),
}

IMAGE_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"generating", "cancelled", "failed"},
    "generating": {"success", "failed", "cancelled"},
    "success": {"superseded"},
    "failed": {"superseded"},
    "cancelled": set(),
    "superseded": set(),
}


def can_transition_batch(current: str, target: str) -> bool:
    return target in BATCH_TRANSITIONS.get(current, set())


def transition_batch(batch: GenerationBatch, target: str) -> None:
    if batch.status == target:
        return
    if not can_transition_batch(batch.status, target):
        raise IllegalTransition(f"批次状态不允许从 {batch.status} 变为 {target}")
    batch.status = target


def transition_image(image: GeneratedImage, target: str) -> None:
    if image.status == target:
        return
    if target not in IMAGE_TRANSITIONS.get(image.status, set()):
        raise IllegalTransition(f"图片状态不允许从 {image.status} 变为 {target}")
    image.status = target


def current_success_images(db: Session, batch_id: int) -> list[GeneratedImage]:
    """每个 index 的最新尝试中，状态为 success 的图片。"""
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
    return [image for image in latest.values() if image.status == "success"]


def recount_completed(db: Session, batch: GenerationBatch) -> int:
    """按当前非 superseded 的成功图数量重算 completed_count。"""
    count = int(
        db.scalar(
            select(func.count())
            .select_from(GeneratedImage)
            .where(
                GeneratedImage.batch_id == batch.id,
                GeneratedImage.status == "success",
            )
        )
        or 0
    )
    if count > batch.total_count:
        count = batch.total_count
    batch.completed_count = max(0, count)
    return batch.completed_count


def summarize_full_status(db: Session, batch: GenerationBatch) -> str:
    """按当前成功张数给出全套批次终态。"""
    success = len(current_success_images(db, batch.id))
    if success >= batch.total_count:
        return "completed"
    if success > 0:
        return "partially_failed"
    return "failed"
