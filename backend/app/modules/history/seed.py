"""历史作品最小 demo 的可重复执行种子夹具。

覆盖 5 号接口文档 §2.6：
- 21 个历史可见批次（18 个 completed + 1 个含 superseded 旧图 + 1 个归档 + 1 个部分失败）
- 1 个示例批次、1 个失败批次（均不进历史）
- demo_dual 的 1 个全套批次（用于跨用户 403，不进入 demo_user 列表）

每个夹具用 `client_request_id=seed-history-*` 标记，重复执行时跳过。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import CreativeSession, GeneratedImage, GenerationBatch
from app.modules.workspace.imaging import make_thumbnail_webp, render_placeholder_png
from app.modules.workspace.storage import storage

SEED_PREFIX = "seed-history-"
SEED_SESSION_TITLE = "历史作品演示"
IMAGE_SIZE = 1000


def _seed_key(name: str) -> str:
    return f"{SEED_PREFIX}{name}"


def _ensure_session(db: Session, user: User) -> CreativeSession:
    """复用同一演示会话，避免每次种子都新建会话。"""
    session = db.scalar(
        select(CreativeSession).where(
            CreativeSession.user_id == user.id,
            CreativeSession.title == SEED_SESSION_TITLE,
        )
    )
    if session is None:
        session = CreativeSession(
            user_id=user.id,
            title=SEED_SESSION_TITLE,
            status="active",
        )
        db.add(session)
        db.flush()
        print(f"[历史种子] 新建演示会话 session_id={session.id}")
    return session


def _ensure_batch(
    db: Session,
    user: User,
    session: CreativeSession,
    key: str,
    *,
    product_name: str,
    batch_type: str,
    status: str,
    total_count: int,
    completed_count: int,
    created_at: datetime,
    style_text: str | None = None,
    source_sample_batch_id: int | None = None,
) -> tuple[GenerationBatch, bool]:
    """按 client_request_id 幂等创建批次。"""
    client_request_id = _seed_key(key)
    existing = db.scalar(
        select(GenerationBatch).where(
            GenerationBatch.client_request_id == client_request_id
        )
    )
    if existing is not None:
        print(f"[历史种子] 批次 {key} 已存在，跳过")
        return existing, False

    batch = GenerationBatch(
        user_id=user.id,
        session_id=session.id,
        batch_type=batch_type,
        source_sample_batch_id=source_sample_batch_id,
        product_name=product_name,
        style_text=style_text,
        width=IMAGE_SIZE,
        height=IMAGE_SIZE,
        template_name=None,
        total_count=total_count,
        completed_count=completed_count,
        status=status,
        stage="done",
        params_snapshot={"seed": "history-demo", "fixture": key},
        requirement_summary=None,
        error_message=None,
        client_request_id=client_request_id,
        started_at=created_at,
        finished_at=created_at + timedelta(minutes=1),
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(batch)
    db.flush()
    print(
        f"[历史种子] 新建批次 {key} batch_id={batch.id} "
        f"status={status} type={batch_type}"
    )
    return batch, True


def _image_paths(
    user_id: int, session_id: int, batch_id: int, index_no: int
) -> tuple[str, str]:
    base = f"generated/{user_id}/{session_id}/{batch_id}/{index_no}"
    return f"{base}.png", f"thumbnails/{user_id}/{session_id}/{batch_id}/{index_no}.webp"


def _write_image_files(
    *,
    user_id: int,
    session_id: int,
    batch_id: int,
    index_no: int,
    content: bytes,
    thumbnail: bytes,
    archived: bool,
) -> tuple[str, str]:
    """写入原件与热存缩略图；归档件只写 archive/ 前缀。"""
    content_path, thumbnail_path = _image_paths(
        user_id, session_id, batch_id, index_no
    )
    storage.save(f"archive/{content_path}" if archived else content_path, content)
    storage.save(thumbnail_path, thumbnail)
    return content_path, thumbnail_path


def _add_image(
    db: Session,
    batch: GenerationBatch,
    *,
    index_no: int,
    status: str,
    image_type: str = "final",
    image_role: str | None = None,
    attempt_no: int = 1,
    is_history_visible: bool = True,
    file_path: str | None = None,
    thumbnail_path: str | None = None,
    error_message: str | None = None,
    archived_at: datetime | None = None,
) -> GeneratedImage:
    """写入一张种子图片记录。"""
    image = GeneratedImage(
        batch_id=batch.id,
        user_id=batch.user_id,
        session_id=batch.session_id,
        image_type=image_type,
        image_role=image_role or ("main" if index_no == 1 else "detail"),
        index_no=index_no,
        attempt_no=attempt_no,
        status=status,
        source_image_id=None,
        file_path=file_path,
        thumbnail_path=thumbnail_path,
        width=IMAGE_SIZE if status == "success" else None,
        height=IMAGE_SIZE if status == "success" else None,
        prompt=None,
        negative_prompt=None,
        model_name=None,
        latency_ms=None,
        error_message=error_message,
        is_history_visible=is_history_visible,
        archived_at=archived_at,
        created_at=batch.created_at + timedelta(seconds=index_no * 2),
        updated_at=batch.created_at + timedelta(seconds=index_no * 2),
    )
    db.add(image)
    return image


def _add_success_images(
    db: Session,
    batch: GenerationBatch,
    indexes: Iterable[int],
    content: bytes,
    thumbnail: bytes,
    *,
    archived: bool = False,
) -> None:
    """为批次写入成功正式图；归档夹具把原件放入 archive/。"""
    for index_no in indexes:
        file_path, thumbnail_path = _write_image_files(
            user_id=batch.user_id,
            session_id=batch.session_id,
            batch_id=batch.id,
            index_no=index_no,
            content=content,
            thumbnail=thumbnail,
            archived=archived,
        )
        _add_image(
            db,
            batch,
            index_no=index_no,
            status="success",
            file_path=file_path,
            thumbnail_path=thumbnail_path,
            archived_at=batch.created_at if archived else None,
        )


def _build_placeholder() -> tuple[bytes, bytes]:
    """生成一套占位 PNG 与缩略图，所有夹具复用同一份字节。"""
    content = render_placeholder_png(
        product_name="历史作品演示",
        role_label="演示",
        index_no=1,
        batch_id=0,
        width=IMAGE_SIZE,
        height=IMAGE_SIZE,
        image_type="final",
    )
    return content, make_thumbnail_webp(content)


def _seed_artifacts_missing(db: Session, user_ids: list[int]) -> bool:
    """检查种子批次的图片记录与本地文件是否完整。"""
    batches = list(
        db.scalars(
            select(GenerationBatch).where(
                GenerationBatch.user_id.in_(user_ids),
                GenerationBatch.client_request_id.like(f"{SEED_PREFIX}%"),
            )
        )
    )
    if not batches:
        return False

    batch_ids = [batch.id for batch in batches]
    images_by_batch: dict[int, list[GeneratedImage]] = {}
    for image in db.scalars(
        select(GeneratedImage).where(GeneratedImage.batch_id.in_(batch_ids))
    ):
        images_by_batch.setdefault(image.batch_id, []).append(image)

    for batch in batches:
        images = images_by_batch.get(batch.id, [])
        success_images = [image for image in images if image.status == "success"]
        if len(success_images) < batch.completed_count:
            print(
                f"[历史种子] 批次 {batch.client_request_id} 图片记录不完整，准备重建"
            )
            return True
        for image in success_images:
            if not image.file_path or not image.thumbnail_path:
                print(f"[历史种子] 图片 {image.id} 缺少路径，准备重建")
                return True
            content_path = (
                f"archive/{image.file_path}"
                if image.archived_at is not None
                else image.file_path
            )
            if not storage.exists(content_path) or not storage.exists(
                image.thumbnail_path
            ):
                print(f"[历史种子] 图片 {image.id} 文件缺失，准备重建")
                return True
    return False


def _reset_seed_batches(db: Session, user_ids: list[int]) -> None:
    """删除种子批次及其图片，随后由 seed_history 重新创建。"""
    batch_ids = list(
        db.scalars(
            select(GenerationBatch.id).where(
                GenerationBatch.user_id.in_(user_ids),
                GenerationBatch.client_request_id.like(f"{SEED_PREFIX}%"),
            )
        )
    )
    if not batch_ids:
        return
    db.execute(delete(GeneratedImage).where(GeneratedImage.batch_id.in_(batch_ids)))
    db.execute(delete(GenerationBatch).where(GenerationBatch.id.in_(batch_ids)))
    db.commit()
    print(f"[历史种子] 已清理 {len(batch_ids)} 个不完整的种子批次")


def seed_history(db: Session) -> int:
    """写入历史作品演示夹具；返回本次新建批次数。"""
    user = db.scalar(select(User).where(User.username == "demo_user"))
    if user is None:
        raise RuntimeError("缺少 demo_user，请先执行登录种子")
    other_user = db.scalar(select(User).where(User.username == "demo_dual"))
    managed_user_ids = [user.id] + ([other_user.id] if other_user else [])

    # 数据库保留但本地存储被清理时，先清理不完整夹具再重建，避免演示全 404
    if _seed_artifacts_missing(db, managed_user_ids):
        _reset_seed_batches(db, managed_user_ids)

    session = _ensure_session(db, user)
    content, thumbnail = _build_placeholder()

    now = datetime.now(timezone.utc)
    base_time = now - timedelta(days=1)
    created = 0

    # 1. 示例批次：不进历史，供 full 批次引用 source_sample_batch_id
    sample, is_new = _ensure_batch(
        db,
        user,
        session,
        "sample",
        product_name="示例演示",
        batch_type="sample",
        status="sample_ready",
        total_count=1,
        completed_count=1,
        created_at=base_time + timedelta(hours=1),
        style_text="简洁白底",
    )
    created += int(is_new)
    if is_new:
        file_path, thumbnail_path = _write_image_files(
            user_id=user.id,
            session_id=session.id,
            batch_id=sample.id,
            index_no=1,
            content=content,
            thumbnail=thumbnail,
            archived=False,
        )
        _add_image(
            db,
            sample,
            index_no=1,
            status="success",
            image_type="sample",
            image_role="main",
            is_history_visible=False,
            file_path=file_path,
            thumbnail_path=thumbnail_path,
        )

    # 2. 18 个普通 completed 批次
    for number in range(1, 19):
        product_name = (
            "秋季/通勤:衬衫" if number == 18 else f"历史通勤衬衫 {number:02d}"
        )
        batch, is_new = _ensure_batch(
            db,
            user,
            session,
            f"completed-{number:02d}",
            product_name=product_name,
            batch_type="full",
            status="completed",
            total_count=6,
            completed_count=6,
            created_at=base_time - timedelta(minutes=number * 10),
            style_text="简洁白底" if number % 2 else None,
            source_sample_batch_id=sample.id,
        )
        if is_new:
            _add_success_images(db, batch, range(1, 7), content, thumbnail)
            created += 1

    # 3. 含 superseded 旧图的 completed 批次
    superseded, is_new = _ensure_batch(
        db,
        user,
        session,
        "superseded",
        product_name="被替代旧图演示",
        batch_type="full",
        status="completed",
        total_count=6,
        completed_count=6,
        created_at=base_time + timedelta(minutes=10),
        style_text="简洁白底",
        source_sample_batch_id=sample.id,
    )
    if is_new:
        _add_image(
            db,
            superseded,
            index_no=1,
            attempt_no=1,
            status="superseded",
            is_history_visible=False,
            error_message="被重生成替代",
        )
        _add_success_images(db, superseded, range(1, 7), content, thumbnail)
        created += 1

    # 4. 归档 completed 批次：原件只在 archive/，缩略图仍在热存储
    archived_batch, is_new = _ensure_batch(
        db,
        user,
        session,
        "archived",
        product_name="归档演示",
        batch_type="full",
        status="completed",
        total_count=6,
        completed_count=6,
        created_at=base_time + timedelta(minutes=20),
        style_text="归档风格",
        source_sample_batch_id=sample.id,
    )
    if is_new:
        _add_success_images(
            db, archived_batch, range(1, 7), content, thumbnail, archived=True
        )
        created += 1

    # 5. 部分失败批次：5 成功 + 1 失败，失败图不进历史
    partial, is_new = _ensure_batch(
        db,
        user,
        session,
        "partially-failed",
        product_name="部分失败演示",
        batch_type="full",
        status="partially_failed",
        total_count=6,
        completed_count=5,
        created_at=base_time + timedelta(minutes=30),
        style_text="简洁白底",
        source_sample_batch_id=sample.id,
    )
    if is_new:
        _add_success_images(db, partial, range(1, 6), content, thumbnail)
        _add_image(
            db,
            partial,
            index_no=6,
            status="failed",
            is_history_visible=False,
            error_message="生图执行失败",
        )
        created += 1

    # 6. 另一个用户的全套批次：用于验证跨用户 403
    if other_user is not None:
        other_session = _ensure_session(db, other_user)
        other_batch, is_new = _ensure_batch(
            db,
            other_user,
            other_session,
            "other-user",
            product_name="其他用户演示",
            batch_type="full",
            status="completed",
            total_count=6,
            completed_count=6,
            created_at=base_time + timedelta(minutes=50),
            style_text="简洁白底",
            source_sample_batch_id=sample.id,
        )
        if is_new:
            _add_success_images(db, other_batch, range(1, 7), content, thumbnail)
            created += 1

    # 7. 失败批次：全部失败，不进历史
    failed, is_new = _ensure_batch(
        db,
        user,
        session,
        "failed",
        product_name="失败批次演示",
        batch_type="full",
        status="failed",
        total_count=6,
        completed_count=0,
        created_at=base_time + timedelta(minutes=40),
        style_text=None,
        source_sample_batch_id=sample.id,
    )
    if is_new:
        for index_no in range(1, 7):
            _add_image(
                db,
                failed,
                index_no=index_no,
                status="failed",
                is_history_visible=False,
                error_message="整批生成失败",
            )
        created += 1

    db.commit()
    print(
        f"[历史种子] 完成：本次新建 {created} 个批次；"
        "期望历史可见 21 个（18 completed + superseded + archived + partial）"
    )
    return created
