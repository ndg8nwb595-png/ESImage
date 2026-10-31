"""内容追溯：用户 → 会话 → 批次 → 图片与媒体访问。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import AuthContext
from app.core.response import ApiError, ok
from app.models.user import Role, User
from app.models.workspace import CreativeSession, GeneratedImage, GenerationBatch
from app.modules.admin.content.service import (
    content_response,
    download_response,
    get_batch_or_404,
    get_image_or_404,
    get_media_image,
    get_session_or_404,
    get_user_or_404,
    serialize_batch,
    serialize_content_user,
    serialize_image_detail,
    serialize_image_item,
    serialize_session,
    thumbnail_response,
)
from app.modules.admin.service import (
    BATCH_STATUSES,
    BATCH_TYPES,
    IMAGE_ROLES,
    IMAGE_STATUSES,
    ensure_content_access,
    is_super_admin,
    local_day_end_exclusive,
    local_day_start,
    page_payload,
    parse_date_range,
    require_permission,
    validate_keyword,
    validate_pagination,
)

router = APIRouter(prefix="/admin/content", tags=["admin-content"])

CONTENT_PERMISSION = require_permission("admin.content.view")


@router.get("/users")
def list_content_users(
    keyword: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    auth: AuthContext = Depends(CONTENT_PERMISSION),
    db: Session = Depends(get_db),
) -> dict:
    """有生成记录的用户列表；管理员过滤超管账号。"""
    keyword_value = validate_keyword(keyword)
    page_number, size = validate_pagination(page, page_size)

    batch_stats = (
        select(
            GenerationBatch.user_id.label("user_id"),
            func.max(GenerationBatch.created_at).label("last_generated_at"),
            func.count().label("batch_count"),
        )
        .group_by(GenerationBatch.user_id)
        .subquery()
    )

    conditions = []
    if not is_super_admin(auth):
        conditions.append(~User.roles.any(Role.code == "super_admin"))
    if keyword_value is not None:
        pattern = f"%{keyword_value}%"
        conditions.append(
            or_(User.username.ilike(pattern), User.display_name.ilike(pattern))
        )

    base = (
        select(User, batch_stats.c.last_generated_at, batch_stats.c.batch_count)
        .join(batch_stats, User.id == batch_stats.c.user_id)
        .where(*conditions)
    )
    total = int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .join(batch_stats, User.id == batch_stats.c.user_id)
            .where(*conditions)
        )
        or 0
    )
    rows = db.execute(
        base.order_by(
            batch_stats.c.last_generated_at.desc(), User.id.desc()
        )
        .offset((page_number - 1) * size)
        .limit(size)
    ).all()

    items = [serialize_content_user(user, last, count) for user, last, count in rows]
    print(f"[生图记录] 用户列表 keyword={keyword_value} 共 {total} 条")
    return ok(page_payload(items, total, page_number, size))


@router.get("/users/{user_id}/sessions")
def list_user_sessions(
    user_id: int,
    page: int = Query(1),
    page_size: int = Query(20),
    auth: AuthContext = Depends(CONTENT_PERMISSION),
    db: Session = Depends(get_db),
) -> dict:
    """用户会话列表，包含 active 与 hidden。"""
    user = get_user_or_404(db, user_id)
    ensure_content_access(db, auth, user.id)
    page_number, size = validate_pagination(page, page_size)

    batch_stats = (
        select(
            GenerationBatch.session_id.label("session_id"),
            func.count().label("batch_count"),
            func.max(GenerationBatch.created_at).label("latest_batch_at"),
        )
        .group_by(GenerationBatch.session_id)
        .subquery()
    )

    base = (
        select(
            CreativeSession,
            func.coalesce(batch_stats.c.batch_count, 0).label("batch_count"),
            batch_stats.c.latest_batch_at,
        )
        .outerjoin(batch_stats, CreativeSession.id == batch_stats.c.session_id)
        .where(CreativeSession.user_id == user.id)
    )
    total = int(
        db.scalar(
            select(func.count())
            .select_from(CreativeSession)
            .where(CreativeSession.user_id == user.id)
        )
        or 0
    )
    rows = db.execute(
        base.order_by(
            func.coalesce(
                CreativeSession.last_message_at, CreativeSession.created_at
            ).desc(),
            CreativeSession.id.desc(),
        )
        .offset((page_number - 1) * size)
        .limit(size)
    ).all()

    items = [
        serialize_session(session, count, latest) for session, count, latest in rows
    ]
    print(f"[生图记录] 用户 {user.id} 会话列表共 {total} 条")
    return ok(page_payload(items, total, page_number, size))


@router.get("/sessions/{session_id}/batches")
def list_session_batches(
    session_id: int,
    product_name: str | None = Query(None),
    batch_type: str | None = Query(None),
    status: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    auth: AuthContext = Depends(CONTENT_PERMISSION),
    db: Session = Depends(get_db),
) -> dict:
    """会话批次列表；支持商品名称、类型、状态与创建时间筛选。"""
    session = get_session_or_404(db, session_id)
    ensure_content_access(db, auth, session.user_id)
    page_number, size = validate_pagination(page, page_size)

    type_value = (batch_type or "all").strip()
    if type_value not in BATCH_TYPES | {"all"}:
        raise ApiError(400, 10003, "参数格式错误")
    status_value = (status or "all").strip()
    if status_value not in BATCH_STATUSES | {"all"}:
        raise ApiError(400, 10003, "参数格式错误")

    product_keyword = validate_keyword(product_name, 60)
    start, end = parse_date_range(start_date, end_date)

    conditions = [GenerationBatch.session_id == session.id]
    if product_keyword is not None:
        conditions.append(GenerationBatch.product_name.ilike(f"%{product_keyword}%"))
    if type_value != "all":
        conditions.append(GenerationBatch.batch_type == type_value)
    if status_value != "all":
        conditions.append(GenerationBatch.status == status_value)
    if start is not None:
        conditions.append(GenerationBatch.created_at >= local_day_start(start))
    if end is not None:
        conditions.append(GenerationBatch.created_at < local_day_end_exclusive(end))

    total = int(
        db.scalar(
            select(func.count()).select_from(GenerationBatch).where(*conditions)
        )
        or 0
    )
    batches = list(
        db.scalars(
            select(GenerationBatch)
            .where(*conditions)
            .order_by(GenerationBatch.created_at.desc(), GenerationBatch.id.desc())
            .offset((page_number - 1) * size)
            .limit(size)
        )
    )
    items = [serialize_batch(batch) for batch in batches]
    print(
        f"[批次筛选] session={session.id} type={type_value} status={status_value} 命中 {total} 条"
    )
    return ok(page_payload(items, total, page_number, size))


@router.get("/batches/{batch_id}/images")
def list_batch_images(
    batch_id: int,
    image_role: str | None = Query(None),
    status: str | None = Query(None),
    include_superseded: bool = Query(False),
    page: int = Query(1),
    page_size: int = Query(20),
    auth: AuthContext = Depends(CONTENT_PERMISSION),
    db: Session = Depends(get_db),
) -> dict:
    """批次图片网格；默认每个序号只返回最新一次尝试。"""
    batch = get_batch_or_404(db, batch_id)
    ensure_content_access(db, auth, batch.user_id)
    page_number, size = validate_pagination(page, page_size)

    role_value = (image_role or "all").strip()
    if role_value not in IMAGE_ROLES | {"all"}:
        raise ApiError(400, 10003, "参数格式错误")
    status_value = (status or "all").strip()
    if status_value not in IMAGE_STATUSES | {"all"}:
        raise ApiError(400, 10003, "参数格式错误")

    include_all = include_superseded or status_value == "superseded"

    conditions = [GeneratedImage.batch_id == batch.id]
    if role_value != "all":
        conditions.append(GeneratedImage.image_role == role_value)
    if status_value != "all":
        conditions.append(GeneratedImage.status == status_value)

    order_by = (
        GeneratedImage.index_no.asc(),
        GeneratedImage.attempt_no.desc(),
        GeneratedImage.id.desc(),
    )

    if include_all:
        total = int(
            db.scalar(
                select(func.count()).select_from(GeneratedImage).where(*conditions)
            )
            or 0
        )
        images = list(
            db.scalars(
                select(GeneratedImage)
                .where(*conditions)
                .order_by(*order_by)
                .offset((page_number - 1) * size)
                .limit(size)
            )
        )
    else:
        # 窗口函数按 index_no 取最新尝试（attempt_no 最大，同值取 id 最大）
        ranked = (
            select(
                GeneratedImage.id.label("image_id"),
                func.row_number()
                .over(
                    partition_by=GeneratedImage.index_no,
                    order_by=(
                        GeneratedImage.attempt_no.desc(),
                        GeneratedImage.id.desc(),
                    ),
                )
                .label("row_no"),
            )
            .where(*conditions)
            .subquery()
        )
        latest_ids = select(ranked.c.image_id).where(ranked.c.row_no == 1)
        total = int(
            db.scalar(select(func.count()).select_from(latest_ids.subquery())) or 0
        )
        images = list(
            db.scalars(
                select(GeneratedImage)
                .where(GeneratedImage.id.in_(latest_ids))
                .order_by(*order_by)
                .offset((page_number - 1) * size)
                .limit(size)
            )
        )

    items = [serialize_image_item(image) for image in images]
    print(
        f"[图片网格] batch={batch.id} role={role_value} status={status_value} "
        f"include_superseded={include_all} 返回 {len(items)}/{total} 张"
    )
    return ok(page_payload(items, total, page_number, size))


@router.get("/images/{image_id}")
def get_image_detail(
    image_id: int,
    auth: AuthContext = Depends(CONTENT_PERMISSION),
    db: Session = Depends(get_db),
) -> dict:
    """单图详情。"""
    image = get_image_or_404(db, image_id)
    ensure_content_access(db, auth, image.user_id)
    data = serialize_image_detail(db, image)
    print(f"[单图详情] image={image.id} user={image.user_id} archived={bool(image.archived_at)}")
    return ok(data)


@router.get("/images/{image_id}/thumbnail")
def get_image_thumbnail(
    image_id: int,
    auth: AuthContext = Depends(CONTENT_PERMISSION),
    db: Session = Depends(get_db),
):
    """缩略图：始终读取热存储 thumbnails/。"""
    image = get_media_image(db, auth, image_id)
    return thumbnail_response(image)


@router.get("/images/{image_id}/content")
def get_image_content(
    image_id: int,
    auth: AuthContext = Depends(CONTENT_PERMISSION),
    db: Session = Depends(get_db),
):
    """大图预览：归档图从 archive/ 读取。"""
    image = get_media_image(db, auth, image_id)
    return content_response(image)


@router.get("/images/{image_id}/download")
def download_image(
    image_id: int,
    auth: AuthContext = Depends(CONTENT_PERMISSION),
    db: Session = Depends(get_db),
):
    """下载原图：归档图从 archive/ 读取。"""
    image = get_media_image(db, auth, image_id)
    return download_response(db, image)
