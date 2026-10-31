"""示例批次、批次查询、确认全套、图片预览与下载。"""

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
from app.models.workspace import CreativeSession, GeneratedImage, GenerationBatch, UploadedAsset
from app.modules.workspace.pipeline import run_full_pipeline, run_sample_pipeline
from app.modules.workspace.schemas import ConfirmGenerationRequest, SampleGenerationRequest
from app.modules.workspace.service import (
    get_owned_session,
    image_content_url,
    image_thumbnail_url,
    now_utc,
    require_permission,
    safe_filename_part,
    filename_timestamp,
    session_title_from_product,
    to_iso,
    validate_idempotency_key,
    validate_product_name,
    validate_size,
    validate_style_text,
    validate_template_id,
    workspace_lock,
)
from app.modules.workspace.storage import storage

router = APIRouter(tags=["workspace"])

FULL_IMAGE_COUNT = 6


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


def _validate_uploads(
    db: Session,
    user_id: int,
    upload_ids: list[int] | None,
    target_session_id: int | None,
) -> list[UploadedAsset]:
    """校验上传图归属、状态、数量与绑定会话，并按提交顺序返回。"""
    if not upload_ids:
        return []
    if len(upload_ids) > 5 or len(set(upload_ids)) != len(upload_ids):
        raise ApiError(400, 30006, "上传文件不符合要求")

    assets = list(
        db.scalars(select(UploadedAsset).where(UploadedAsset.id.in_(upload_ids)))
    )
    assets_by_id = {asset.id: asset for asset in assets}
    ordered: list[UploadedAsset] = []
    for upload_id in upload_ids:
        asset = assets_by_id.get(upload_id)
        if asset is None or asset.user_id != user_id or asset.status != "active":
            raise ApiError(400, 30006, "上传文件不符合要求")
        # 未绑定会话的上传图可随本次生成绑定；已绑定其他会话的不可复用
        if asset.session_id is not None and asset.session_id != target_session_id:
            raise ApiError(400, 30006, "上传文件不符合要求")
        ordered.append(asset)
    return ordered


def _running_batch_count(db: Session, user_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(GenerationBatch)
            .where(
                GenerationBatch.user_id == user_id,
                GenerationBatch.status.in_(("queued", "running")),
            )
        )
        or 0
    )


def _image_payload(image: GeneratedImage, batch: GenerationBatch) -> dict:
    has_file = bool(image.file_path)
    has_thumbnail = bool(image.thumbnail_path)
    return {
        "image_id": image.id,
        "index": image.index_no,
        "image_role": image.image_role,
        "status": image.status,
        "thumbnail_url": image_thumbnail_url(image.id) if has_thumbnail else None,
        "content_url": image_content_url(image.id) if has_file else None,
        "error_message": image.error_message,
        "width": image.width if image.width is not None else batch.width,
        "height": image.height if image.height is not None else batch.height,
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
    validate_template_id(payload.template_id)

    # 进程内锁：把幂等查询、并发计数、上传图校验与插入放在同一临界区
    with workspace_lock():
        # 幂等：相同 client_request_id 直接返回已有批次，不重复创建/投递
        existing = db.scalar(
            select(GenerationBatch).where(GenerationBatch.client_request_id == client_request_id)
        )
        if existing is not None:
            if existing.user_id != auth.user.id or existing.batch_type != "sample":
                raise ApiError(409, 30005, "请求已处理")
            print(f"[生成] 幂等命中 client_request_id={client_request_id} batch_id={existing.id}")
            return ok(_sample_payload(db, existing))

        # 并发：同一用户只允许 1 个 queued/running 批次
        if _running_batch_count(db, auth.user.id) > 0:
            raise ApiError(409, 30003, "已有生成任务进行中")

        session: CreativeSession | None = None
        if payload.session_id is not None:
            session = get_owned_session(db, auth.user.id, payload.session_id)

        uploads = _validate_uploads(
            db, auth.user.id, payload.upload_ids, session.id if session else None
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

        # 按 upload_ids 顺序回填 session_id 与 sort_order
        for index, asset in enumerate(uploads):
            asset.session_id = session.id
            asset.sort_order = index

        summary = (
            payload.requirement_summary
            if payload.requirement_summary is not None
            else session.requirement_summary
        )
        snapshot = {
            "product_name": product_name,
            "style_text": style_text,
            "width": width,
            "height": height,
            "template_id": None,
            "upload_ids": [asset.id for asset in uploads],
            "image_composition": "1 main + 5 detail",
            "requirement_summary": summary,
            "created_at": to_iso(now_utc()),
        }

        batch = GenerationBatch(
            user_id=auth.user.id,
            session_id=session.id,
            batch_type="sample",
            source_sample_batch_id=None,
            product_name=product_name,
            style_text=style_text,
            width=width,
            height=height,
            template_name=None,
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
            db.commit()
        except IntegrityError:
            # 并发提交同一 client_request_id：返回已创建批次
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
            f"[生成] 创建示例批次 batch_id={batch.id} session_id={session.id} user={auth.user.id}"
        )
        background_tasks.add_task(run_sample_pipeline, batch.id)
        return ok(_sample_payload(db, batch))


@router.get("/generations/{batch_id}")
def get_batch(
    batch_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """查询批次状态、阶段进度与图片列表。"""
    batch = db.get(GenerationBatch, batch_id)
    if batch is None or batch.user_id != auth.user.id:
        raise ApiError(404, 30004, "批次不存在")

    images = list(
        db.scalars(
            select(GeneratedImage)
            .where(
                GeneratedImage.batch_id == batch.id,
                GeneratedImage.status != "superseded",
            )
            .order_by(GeneratedImage.index_no.asc(), GeneratedImage.attempt_no.desc())
        )
    )
    return ok(
        {
            "batch_id": batch.id,
            "batch_type": batch.batch_type,
            "status": batch.status,
            "stage": batch.stage,
            "total_count": batch.total_count,
            "completed_count": batch.completed_count,
            "images": [_image_payload(image, batch) for image in images],
            "error_message": batch.error_message,
            "created_at": to_iso(batch.created_at),
            "finished_at": to_iso(batch.finished_at),
        }
    )


def _full_payload(batch: GenerationBatch) -> dict:
    return {
        "full_batch_id": batch.id,
        "total_count": batch.total_count,
        "status": batch.status,
    }


@router.post("/generations/{batch_id}/confirm")
def confirm_batch(
    batch_id: int,
    payload: ConfirmGenerationRequest,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> dict:
    """确认示例批次并创建全套批次；示例图复用为第 1 张主图。"""
    client_request_id = validate_idempotency_key(payload.client_request_id, "client_request_id")

    # 进程内锁串行化确认；锁内重新做幂等判定，避免并发同 key 返回 409 或触发 500
    with workspace_lock():
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

        # 在事务中对示例批次加行锁，避免重复确认
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
        if sample.batch_type != "sample":
            raise ApiError(409, 30005, "当前批次状态不允许确认")
        if sample.status != "sample_ready":
            raise ApiError(409, 30005, "当前批次状态不允许确认")

        latest_confirmable_id = db.scalar(
            select(GenerationBatch.id)
            .where(
                GenerationBatch.user_id == auth.user.id,
                GenerationBatch.batch_type == "sample",
                GenerationBatch.status == "sample_ready",
            )
            .order_by(GenerationBatch.created_at.desc(), GenerationBatch.id.desc())
            .limit(1)
        )
        if latest_confirmable_id != sample.id:
            raise ApiError(409, 30005, "该示例不是最新示例，请确认最新示例")

        if _running_batch_count(db, auth.user.id) > 0:
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
            params_snapshot=sample.params_snapshot,
            requirement_summary=sample.requirement_summary,
            client_request_id=client_request_id,
        )
        db.add(full_batch)

        try:
            db.flush()
            # 示例图作为全套第 1 张主图，复用文件路径，不重复生成
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
            sample.status = "confirmed"
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


def _get_owned_image(db: Session, user_id: int, image_id: int) -> GeneratedImage:
    image = db.get(GeneratedImage, image_id)
    if image is None or image.user_id != user_id:
        raise ApiError(404, 30014, "文件不存在")
    return image


@router.get("/images/{image_id}/content")
def get_image_content(
    image_id: int,
    auth: AuthContext = Depends(require_permission("user.generate")),
    db: Session = Depends(get_db),
) -> FileResponse:
    """大图预览：示例图与正式图都可读，下载权限由下载接口单独控制。"""
    image = _get_owned_image(db, auth.user.id, image_id)
    if not image.file_path:
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
    """结果网格缩略图（与 5 号文档的接口约定保持一致）。"""
    image = _get_owned_image(db, auth.user.id, image_id)
    if not image.thumbnail_path:
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
    """下载正式图 PNG；示例图确认前、失败图、取消半成品不可下载。"""
    image = _get_owned_image(db, auth.user.id, image_id)

    if image.image_type == "sample":
        raise ApiError(409, 30005, "示例图确认前不可下载")
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

    role_label = "主图" if image.image_role == "main" else "详情图"
    filename = (
        f"{safe_filename_part(batch.product_name)}_{role_label}_"
        f"{image.index_no}_{filename_timestamp(image.created_at)}.png"
    )
    return FileResponse(
        path,
        media_type="image/png",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, max-age=300",
        },
    )
