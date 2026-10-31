"""生图任务接口：示例批次、全套确认、取消、单张重试、预览/下载与整组 ZIP。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext
from app.core.response import ApiError, ok
from app.core.storage import storage
from app.models.workspace import CreativeSession, GeneratedImage, GenerationBatch
from app.modules.generation.pipeline import (
    run_full_pipeline,
    run_regenerate_pipeline,
    run_sample_pipeline,
)
from app.modules.generation.schemas import (
    ConfirmGenerationRequest,
    RegenerateImageRequest,
    SampleGenerationRequest,
)
from app.modules.generation.service import (
    FULL_IMAGE_COUNT,
    build_params_snapshot,
    generation_lock,
    get_active_template,
    get_owned_batch,
    get_owned_image,
    get_owned_session,
    image_download_filename,
    latest_confirmable_sample_id,
    now_utc,
    require_permission,
    running_batch_count,
    session_title_from_product,
    to_iso,
    validate_idempotency_key,
    validate_product_name,
    validate_size,
    validate_style_text,
    validate_uploads,
    batch_payload,
)
from app.modules.generation.state import transition_batch, transition_image

router = APIRouter(tags=["generation"])


def _sample_payload(db: Session, batch: GenerationBatch) -> dict:
    session = db.get(CreativeSession, batch.session_id)
    return {
        "batch_id": batch.id,
        "session_id": batch.session_id,
        "session_title": session.title if session else None,
        "batch_type": batch.batch_type,
        "status": batch.status,
        "total_count": batch.total_count,
        "completed_count": batch.completed_count,
    }


def _full_payload(batch: GenerationBatch) -> dict:
    return {
        "full_batch_id": batch.id,
        "total_count": batch.total_count,
        "status": batch.status,
    }


@router.post("/generations/sample")
def create_sample_batch(
    payload: SampleGenerationRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """创建示例批次；无 session_id 时在同一事务内创建会话。"""
    client_request_id = validate_idempotency_key(payload.client_request_id, "client_request_id")
    product_name = validate_product_name(payload.product_name)
    style_text = validate_style_text(payload.style_text)
    width, height = validate_size(payload.width, payload.height)

    with generation_lock():
        existing = db.scalar(
            select(GenerationBatch).where(
                GenerationBatch.client_request_id == client_request_id
            )
        )
        if existing is not None:
            if existing.user_id != auth.user.id or existing.batch_type != "sample":
                raise ApiError(409, 30005, "请求已处理")
            return ok(_sample_payload(db, existing))

        if running_batch_count(db, auth.user.id) > 0:
            raise ApiError(409, 30003, "已有生成任务进行中")

        template = get_active_template(db, payload.template_id)
        if style_text is None and template is not None and template.style_text:
            style_text = template.style_text

        session: CreativeSession | None = None
        if payload.session_id is not None:
            session = get_owned_session(db, auth.user.id, payload.session_id)

        uploads = validate_uploads(
            db,
            auth.user.id,
            payload.upload_ids,
            session.id if session else None,
        )

        if session is None:
            session = CreativeSession(
                user_id=auth.user.id,
                title=session_title_from_product(product_name),
                status="active",
            )
            db.add(session)
            db.flush()
        session.last_message_at = now_utc()

        for index, asset in enumerate(uploads):
            asset.session_id = session.id
            asset.sort_order = index

        summary = (
            payload.requirement_summary
            if payload.requirement_summary is not None
            else session.requirement_summary
        )
        snapshot = build_params_snapshot(
            product_name=product_name,
            style_text=style_text,
            width=width,
            height=height,
            template=template,
            upload_ids=[asset.id for asset in uploads],
            requirement_summary=summary,
        )

        batch = GenerationBatch(
            user_id=auth.user.id,
            session_id=session.id,
            batch_type="sample",
            source_sample_batch_id=None,
            product_name=product_name,
            style_text=style_text,
            width=width,
            height=height,
            template_name=template.name if template else None,
            total_count=1,
            completed_count=0,
            status="queued",
            stage=None,
            params_snapshot=snapshot,
            requirement_summary=summary,
            client_request_id=client_request_id,
        )
        db.add(batch)
        try:
            db.flush()
            db.add(
                GeneratedImage(
                    batch_id=batch.id,
                    user_id=auth.user.id,
                    session_id=session.id,
                    image_type="sample",
                    image_role="main",
                    index_no=1,
                    attempt_no=1,
                    status="pending",
                    width=width,
                    height=height,
                )
            )
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(GenerationBatch).where(
                    GenerationBatch.client_request_id == client_request_id
                )
            )
            if existing is None or existing.user_id != auth.user.id:
                raise ApiError(409, 30005, "请求已处理")
            return ok(_sample_payload(db, existing))
        db.refresh(batch)

        print(
            f"[生成] 创建示例批次 batch_id={batch.id} session_id={session.id} "
            f"user={auth.user.id}"
        )
        background_tasks.add_task(run_sample_pipeline, batch.id)
        return ok(_sample_payload(db, batch))


@router.get("/generations/{batch_id}")
def get_batch(
    batch_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """查询批次状态、阶段进度与每个 index 的最新尝试。"""
    batch = get_owned_batch(db, auth.user.id, batch_id)
    return ok(batch_payload(db, batch))


@router.post("/generations/{batch_id}/confirm")
def confirm_batch(
    batch_id: int,
    payload: ConfirmGenerationRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """确认最新示例并创建全套批次；示例图复用为第 1 张主图。"""
    client_request_id = validate_idempotency_key(payload.client_request_id, "client_request_id")

    with generation_lock():
        existing_full = db.scalar(
            select(GenerationBatch).where(
                GenerationBatch.client_request_id == client_request_id,
                GenerationBatch.batch_type == "full",
            )
        )
        if existing_full is not None:
            if existing_full.user_id != auth.user.id:
                raise ApiError(409, 30005, "请求已处理")
            return ok(_full_payload(existing_full))

        sample = db.scalar(
            select(GenerationBatch)
            .where(
                GenerationBatch.id == batch_id,
                GenerationBatch.user_id == auth.user.id,
            )
            .with_for_update()
        )
        if sample is None:
            raise ApiError(404, 30004, "批次不存在")
        if sample.batch_type != "sample" or sample.status != "sample_ready":
            raise ApiError(409, 30005, "当前批次状态不允许确认")

        if latest_confirmable_sample_id(db, auth.user.id) != sample.id:
            raise ApiError(409, 30005, "该示例不是最新示例，请确认最新示例")

        if running_batch_count(db, auth.user.id) > 0:
            raise ApiError(409, 30003, "已有生成任务进行中")

        sample_image = db.scalar(
            select(GeneratedImage)
            .where(
                GeneratedImage.batch_id == sample.id,
                GeneratedImage.image_type == "sample",
                GeneratedImage.status == "success",
            )
            .order_by(GeneratedImage.index_no.asc())
            .limit(1)
        )
        if sample_image is None or not sample_image.file_path:
            raise ApiError(409, 30005, "当前批次状态不允许确认")

        full_batch = GenerationBatch(
            user_id=auth.user.id,
            session_id=sample.session_id,
            batch_type="full",
            source_sample_batch_id=sample.id,
            product_name=sample.product_name,
            style_text=sample.style_text,
            width=sample.width,
            height=sample.height,
            template_name=sample.template_name,
            total_count=FULL_IMAGE_COUNT,
            completed_count=1,
            status="queued",
            stage=None,
            params_snapshot=dict(sample.params_snapshot),
            requirement_summary=sample.requirement_summary,
            client_request_id=client_request_id,
        )
        db.add(full_batch)

        try:
            db.flush()
            # 第 1 张复用示例图文件，不重复生成
            db.add(
                GeneratedImage(
                    batch_id=full_batch.id,
                    user_id=auth.user.id,
                    session_id=sample.session_id,
                    image_type="final",
                    image_role="main",
                    index_no=1,
                    attempt_no=1,
                    status="success",
                    source_image_id=sample_image.id,
                    file_path=sample_image.file_path,
                    thumbnail_path=sample_image.thumbnail_path,
                    width=sample_image.width,
                    height=sample_image.height,
                    model_name=sample_image.model_name,
                    is_history_visible=False,
                )
            )
            for index in range(2, FULL_IMAGE_COUNT + 1):
                db.add(
                    GeneratedImage(
                        batch_id=full_batch.id,
                        user_id=auth.user.id,
                        session_id=sample.session_id,
                        image_type="final",
                        image_role="detail",
                        index_no=index,
                        attempt_no=1,
                        status="pending",
                        width=sample.width,
                        height=sample.height,
                    )
                )
            transition_batch(sample, "confirmed")
            db.commit()
        except IntegrityError:
            db.rollback()
            existing_full = db.scalar(
                select(GenerationBatch).where(
                    GenerationBatch.client_request_id == client_request_id,
                    GenerationBatch.batch_type == "full",
                )
            )
            if existing_full is None or existing_full.user_id != auth.user.id:
                raise ApiError(409, 30005, "请求已处理")
            return ok(_full_payload(existing_full))
        db.refresh(full_batch)

        print(
            f"[生成] 确认示例 batch_id={sample.id} -> full_batch_id={full_batch.id} "
            f"user={auth.user.id}"
        )
        background_tasks.add_task(run_full_pipeline, full_batch.id)
        return ok(_full_payload(full_batch))


@router.post("/generations/{batch_id}/cancel")
def cancel_batch(
    batch_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """取消批次；已取消再次调用自然幂等。"""
    with generation_lock():
        batch = db.scalar(
            select(GenerationBatch)
            .where(
                GenerationBatch.id == batch_id,
                GenerationBatch.user_id == auth.user.id,
            )
            .with_for_update()
        )
        if batch is None:
            raise ApiError(404, 30004, "批次不存在")

        if batch.status == "cancelled":
            return ok(
                {
                    "batch_id": batch.id,
                    "status": batch.status,
                    "finished_at": to_iso(batch.finished_at),
                }
            )

        if batch.batch_type == "sample":
            cancellable = ("queued", "running", "sample_ready")
        else:
            cancellable = ("queued", "running")
        if batch.status not in cancellable:
            raise ApiError(409, 30005, "当前批次状态不允许取消")

        transition_batch(batch, "cancelled")
        batch.finished_at = now_utc()
        for image in db.scalars(
            select(GeneratedImage).where(GeneratedImage.batch_id == batch.id)
        ):
            if image.status == "pending":
                transition_image(image, "cancelled")
            elif image.status == "success":
                image.is_history_visible = False
        db.commit()
        return ok(
            {
                "batch_id": batch.id,
                "status": batch.status,
                "finished_at": to_iso(batch.finished_at),
            }
        )


def _regenerate_payload(image: GeneratedImage) -> dict:
    return {
        "image_id": image.id,
        "batch_id": image.batch_id,
        "index": image.index_no,
        "image_role": image.image_role,
        "attempt_no": image.attempt_no,
        "status": image.status,
    }


@router.post("/images/{image_id}/regenerate")
def regenerate_image(
    image_id: int,
    payload: RegenerateImageRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """单张重试/重生成；新记录 attempt_no+1，旧记录 superseded。"""
    client_request_id = validate_idempotency_key(payload.client_request_id, "client_request_id")

    with generation_lock():
        existing = db.scalar(
            select(GeneratedImage).where(
                GeneratedImage.client_request_id == client_request_id
            )
        )
        if existing is not None:
            if existing.user_id != auth.user.id:
                raise ApiError(409, 30005, "请求已处理")
            return ok(_regenerate_payload(existing))

        image = db.scalar(
            select(GeneratedImage)
            .where(
                GeneratedImage.id == image_id,
                GeneratedImage.user_id == auth.user.id,
            )
            .with_for_update()
        )
        if image is None:
            raise ApiError(404, 30014, "文件不存在")
        if image.image_type != "final" or image.status == "superseded":
            raise ApiError(409, 30005, "当前图片不可重试")

        batch = db.scalar(
            select(GenerationBatch)
            .where(GenerationBatch.id == image.batch_id)
            .with_for_update()
        )
        if batch is None:
            raise ApiError(404, 30014, "文件不存在")
        if batch.batch_type != "full":
            raise ApiError(409, 30005, "当前图片不可重试")
        if batch.status not in ("completed", "partially_failed"):
            raise ApiError(409, 30005, "请从批次入口重新生成")

        max_attempt = db.scalar(
            select(func.max(GeneratedImage.attempt_no)).where(
                GeneratedImage.batch_id == batch.id,
                GeneratedImage.index_no == image.index_no,
            )
        )
        if max_attempt is not None and image.attempt_no != int(max_attempt):
            raise ApiError(409, 30005, "当前图片不可重试")

        # 新图先以 pending 落库、后台任务才置 generating；
        # 两者都要计入，才能覆盖请求与 Worker 之间的并发窗口。
        active_retry = db.scalar(
            select(func.count())
            .select_from(GeneratedImage)
            .where(
                GeneratedImage.batch_id == batch.id,
                GeneratedImage.status.in_(("pending", "generating")),
            )
        )
        if int(active_retry or 0) > 0:
            raise ApiError(409, 30005, "该批次有重试任务进行中")

        new_image = GeneratedImage(
            batch_id=batch.id,
            user_id=auth.user.id,
            session_id=image.session_id,
            image_type=image.image_type,
            image_role=image.image_role,
            index_no=image.index_no,
            attempt_no=image.attempt_no + 1,
            status="pending",
            prompt=image.prompt,
            negative_prompt=image.negative_prompt,
            model_name=image.model_name,
            width=image.width or batch.width,
            height=image.height or batch.height,
            is_history_visible=False,
            client_request_id=client_request_id,
        )
        db.add(new_image)
        try:
            db.flush()
            transition_image(image, "superseded")
            image.is_history_visible = False
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(GeneratedImage).where(
                    GeneratedImage.client_request_id == client_request_id
                )
            )
            if existing is None or existing.user_id != auth.user.id:
                raise ApiError(409, 30005, "请求已处理")
            return ok(_regenerate_payload(existing))
        db.refresh(new_image)

        print(
            f"[生成] 重试图片 image_id={image.id} -> new_image_id={new_image.id} "
            f"batch_id={batch.id} attempt={new_image.attempt_no}"
        )
        background_tasks.add_task(run_regenerate_pipeline, new_image.id)
        return ok(_regenerate_payload(new_image))


@router.get("/images/{image_id}/content")
def get_image_content(
    image_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> FileResponse:
    """大图预览：示例图与当前正式图可读；superseded 旧图不提供。"""
    image = get_owned_image(db, auth.user.id, image_id)
    if image.status == "superseded" or not image.file_path:
        raise ApiError(404, 30014, "文件不存在")
    path = storage.path(image.file_path)
    if not path.is_file():
        raise ApiError(404, 30014, "文件不存在")
    return FileResponse(
        path,
        media_type="image/png",
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": "inline",
        },
    )


@router.get("/images/{image_id}/thumbnail")
def get_image_thumbnail(
    image_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> FileResponse:
    """结果网格缩略图；与 2/5 号 demo 的路径契约保持一致。"""
    image = get_owned_image(db, auth.user.id, image_id)
    if image.status == "superseded" or not image.thumbnail_path:
        raise ApiError(404, 30014, "文件不存在")
    path = storage.path(image.thumbnail_path)
    if not path.is_file():
        raise ApiError(404, 30014, "文件不存在")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": "inline",
        },
    )


@router.get("/images/{image_id}/download")
def download_image(
    image_id: int,
    auth: AuthContext = Depends(require_permission("user.history")),
    db: Session = Depends(get_db),
) -> FileResponse:
    """下载单张正式图 PNG；示例图确认前、失败图、取消半成品不可下载。"""
    image = get_owned_image(db, auth.user.id, image_id)

    if image.image_type == "sample":
        raise ApiError(409, 30005, "示例图确认前不可下载")
    if image.status == "superseded":
        raise ApiError(409, 30005, "当前图片不可下载")
    if image.status != "success" or not image.is_history_visible:
        raise ApiError(409, 30005, "当前图片不可下载")

    batch = db.get(GenerationBatch, image.batch_id)
    if batch is None or batch.status not in ("completed", "partially_failed"):
        raise ApiError(409, 30005, "当前图片不可下载")
    if not image.file_path:
        raise ApiError(404, 30014, "文件不存在")

    path = storage.path(image.file_path)
    if not path.is_file():
        raise ApiError(404, 30014, "文件不存在")

    filename = image_download_filename(batch, image)
    return FileResponse(
        path,
        media_type="image/png",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, max-age=300",
        },
    )
