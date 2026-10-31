"""最小 demo 的演示生成管线。

不调用真实 8 Agent / 豆包模型，只按接口文档约定的阶段推进并产出占位 PNG。
PRD 4 的正式实现可替换本文件内部，对外接口与数据字段保持不变。
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.workspace import GeneratedImage, GenerationBatch
from app.modules.workspace.imaging import make_thumbnail_webp, render_placeholder_png
from app.modules.workspace.storage import storage

logger = logging.getLogger("esimage.workspace.pipeline")

# 示例批次阶段顺序（对齐接口文档 §6.2）
SAMPLE_STAGES = [
    "product_understanding",
    "copywriter",
    "prompt_builder",
    "image_generator",
    "quality_reviewer",
    "text_composition",
    "done",
]

DETAIL_COUNT = 5


def _sleep() -> None:
    """阶段停顿，便于前端轮询观察进度；测试可设 0。"""
    delay = settings.DEMO_PIPELINE_STAGE_DELAY
    if delay > 0:
        time.sleep(delay)


def _set_stage(db, batch: GenerationBatch, stage: str) -> None:
    batch.stage = stage
    db.commit()


def _render_and_store(
    *,
    user_id: int,
    product_name: str,
    role_label: str,
    index_no: int,
    batch_id: int,
    width: int,
    height: int,
    image_type: str,
) -> tuple[str, str]:
    """生成占位 PNG 与缩略图，返回相对存储路径。"""
    png = render_placeholder_png(
        product_name=product_name,
        role_label=role_label,
        index_no=index_no,
        batch_id=batch_id,
        width=width,
        height=height,
        image_type=image_type,
    )
    token = uuid.uuid4().hex
    file_path = f"generated/{user_id}/{token}.png"
    thumbnail_path = f"thumbnails/{user_id}/{token}.webp"
    storage.save(file_path, png)
    storage.save(thumbnail_path, make_thumbnail_webp(png))
    return file_path, thumbnail_path


def _create_image(
    db,
    batch: GenerationBatch,
    *,
    index_no: int,
    image_role: str,
    image_type: str,
) -> GeneratedImage:
    """创建一张生成中图片并落库。"""
    image = GeneratedImage(
        batch_id=batch.id,
        user_id=batch.user_id,
        session_id=batch.session_id,
        image_type=image_type,
        image_role=image_role,
        index_no=index_no,
        attempt_no=1,
        status="generating",
        width=batch.width,
        height=batch.height,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


def _finish_image(
    db,
    batch: GenerationBatch,
    image: GeneratedImage,
    *,
    role_label: str,
) -> None:
    """产出占位图并把图片置为成功。"""
    started = time.perf_counter()
    file_path, thumbnail_path = _render_and_store(
        user_id=batch.user_id,
        product_name=batch.product_name,
        role_label=role_label,
        index_no=image.index_no,
        batch_id=batch.id,
        width=batch.width,
        height=batch.height,
        image_type=batch.batch_type,
    )
    image.file_path = file_path
    image.thumbnail_path = thumbnail_path
    image.status = "success"
    image.model_name = "demo-placeholder"
    image.latency_ms = int((time.perf_counter() - started) * 1000)
    db.commit()


def _recount_completed(db, batch: GenerationBatch) -> int:
    """按当前成功张数重算 completed_count。"""
    count = db.scalar(
        select(func.count())
        .select_from(GeneratedImage)
        .where(
            GeneratedImage.batch_id == batch.id,
            GeneratedImage.status == "success",
        )
    )
    batch.completed_count = int(count or 0)
    db.commit()
    return batch.completed_count


def run_sample_pipeline(batch_id: int) -> None:
    """示例批次：queued -> running -> sample_ready。"""
    with SessionLocal() as db:
        batch = db.get(GenerationBatch, batch_id)
        if batch is None or batch.status != "queued":
            logger.info("示例批次 %s 不是 queued，跳过演示管线", batch_id)
            return

        try:
            batch.status = "running"
            batch.started_at = datetime.now(timezone.utc)
            db.commit()

            image: GeneratedImage | None = None
            for stage in SAMPLE_STAGES:
                _set_stage(db, batch, stage)
                if stage == "image_generator":
                    image = _create_image(db, batch, index_no=1, image_role="main", image_type="sample")
                    _finish_image(db, batch, image, role_label="主图")
                    _recount_completed(db, batch)
                _sleep()

            batch.status = "sample_ready"
            batch.stage = "done"
            batch.finished_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("示例批次 %s 生成完成", batch_id)
        except Exception as exc:  # 演示管线兜底：记录失败原因，不抛出后台线程
            logger.exception("示例批次 %s 生成失败", batch_id)
            db.rollback()
            batch = db.get(GenerationBatch, batch_id)
            if batch is not None:
                batch.status = "failed"
                batch.error_message = str(exc)[:1000]
                batch.finished_at = datetime.now(timezone.utc)
                db.commit()


def run_full_pipeline(batch_id: int) -> None:
    """全套批次：queued -> running -> completed，第 1 张复用示例图。"""
    with SessionLocal() as db:
        batch = db.get(GenerationBatch, batch_id)
        if batch is None or batch.status != "queued":
            logger.info("全套批次 %s 不是 queued，跳过演示管线", batch_id)
            return

        try:
            batch.status = "running"
            batch.started_at = datetime.now(timezone.utc)
            db.commit()

            # 与示例批次一致，先展示需求理解、文案与提示词阶段
            for stage in ("product_understanding", "copywriter", "prompt_builder"):
                _set_stage(db, batch, stage)
                _sleep()

            detail_indexes = list(range(2, DETAIL_COUNT + 2))
            for index_no in detail_indexes:
                existing = db.scalar(
                    select(GeneratedImage).where(
                        GeneratedImage.batch_id == batch.id,
                        GeneratedImage.index_no == index_no,
                        GeneratedImage.image_type == "final",
                        GeneratedImage.status == "success",
                    )
                )
                if existing is not None:
                    continue

                _set_stage(db, batch, "image_generator")
                image = _create_image(
                    db, batch, index_no=index_no, image_role="detail", image_type="final"
                )
                _finish_image(db, batch, image, role_label="详情图")
                _recount_completed(db, batch)
                _sleep()

            _set_stage(db, batch, "quality_reviewer")
            _sleep()
            _set_stage(db, batch, "text_composition")
            _sleep()

            batch.status = "completed"
            batch.stage = "done"
            batch.finished_at = datetime.now(timezone.utc)

            # completed 与 is_history_visible 必须在同一事务提交：
            # 避免前端刚看到 completed 就下载却拿到 30005
            count = db.scalar(
                select(func.count())
                .select_from(GeneratedImage)
                .where(
                    GeneratedImage.batch_id == batch.id,
                    GeneratedImage.status == "success",
                )
            )
            batch.completed_count = int(count or 0)

            # 全套完成后，正式图才进入历史作品
            for image in db.scalars(
                select(GeneratedImage).where(
                    GeneratedImage.batch_id == batch.id,
                    GeneratedImage.image_type == "final",
                    GeneratedImage.status == "success",
                )
            ):
                image.is_history_visible = True
            db.commit()
            logger.info("全套批次 %s 生成完成", batch_id)
        except Exception as exc:
            logger.exception("全套批次 %s 生成失败", batch_id)
            db.rollback()
            batch = db.get(GenerationBatch, batch_id)
            if batch is not None:
                batch.status = "failed"
                batch.error_message = str(exc)[:1000]
                batch.finished_at = datetime.now(timezone.utc)
                db.commit()
