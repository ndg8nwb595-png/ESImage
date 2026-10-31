"""7 号管理后台幂等演示数据种子。

覆盖多用户、会话、批次、图片、Agent 调用与归档文件；不调用豆包、不写导出数据。
种子以用户名、批次幂等键与图片序号为唯一键，重复执行不重复创建、不覆盖已有修改。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.models.workspace import AgentRun, CreativeSession, GeneratedImage, GenerationBatch
from app.modules.admin.service import AGENT_NAMES
from app.modules.workspace.imaging import make_thumbnail_webp, render_placeholder_png
from app.modules.workspace.storage import storage

TEXT_MODEL = "doubao-seed-1.6"
IMAGE_MODEL = "doubao-seedream-4.0"
SEED_PREFIX = "seed7"
ARCHIVE_DAY_OFFSET = 0

_TERMINAL_BATCH_STATUSES = {
    "sample_ready",
    "confirmed",
    "completed",
    "partially_failed",
    "failed",
    "cancelled",
}


def _at(base_date, day_offset: int, hour: int = 10, minute: int = 0) -> datetime:
    """生成 Asia/Shanghai 的指定日期时间。"""
    value = base_date - timedelta(days=day_offset)
    return datetime(value.year, value.month, value.day, hour, minute, tzinfo=settings.TZ)


def _get_user(db: Session, username: str) -> User:
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise RuntimeError(f"种子依赖的演示账号不存在：{username}")
    return user


def _ensure_session(
    db: Session,
    *,
    user: User,
    title: str,
    status: str,
    created_at: datetime,
    last_message_at: datetime | None,
    product_name: str,
) -> CreativeSession:
    session = db.scalar(
        select(CreativeSession).where(
            CreativeSession.user_id == user.id, CreativeSession.title == title
        )
    )
    if session is not None:
        return session
    session = CreativeSession(
        user_id=user.id,
        title=title,
        status=status,
        requirement_summary={
            "product_name": product_name,
            "category": None,
            "selling_points": [],
            "target_audience": None,
            "scenes": [],
            "tone": None,
            "constraints": [],
            "seed": SEED_PREFIX,
        },
        last_message_at=last_message_at,
        created_at=created_at,
        updated_at=last_message_at or created_at,
    )
    db.add(session)
    db.flush()
    print(f"[种子] 新建会话 {title}（user={user.username}, status={status}）")
    return session


def _ensure_batch(
    db: Session,
    *,
    user: User,
    session: CreativeSession,
    batch_type: str,
    status: str,
    product_name: str,
    style_text: str | None,
    width: int,
    height: int,
    total_count: int,
    completed_count: int,
    created_at: datetime,
    marker: str,
    source_sample_batch_id: int | None = None,
    template_name: str | None = "简约白底",
) -> GenerationBatch:
    existing = db.scalar(
        select(GenerationBatch).where(GenerationBatch.client_request_id == marker)
    )
    if existing is not None:
        return existing

    finished_at = (
        created_at + timedelta(minutes=6)
        if status in _TERMINAL_BATCH_STATUSES
        else None
    )
    batch = GenerationBatch(
        user_id=user.id,
        session_id=session.id,
        batch_type=batch_type,
        source_sample_batch_id=source_sample_batch_id,
        product_name=product_name,
        style_text=style_text,
        width=width,
        height=height,
        template_name=template_name,
        total_count=total_count,
        completed_count=completed_count,
        status=status,
        stage="done" if status in _TERMINAL_BATCH_STATUSES else None,
        params_snapshot={
            "product_name": product_name,
            "style_text": style_text,
            "width": width,
            "height": height,
            "template_id": None,
            "template_name": template_name,
            "image_composition": (
                "1 main + 0 detail"
                if batch_type == "sample"
                else f"1 main + {max(0, total_count - 1)} detail"
            ),
            "seed": SEED_PREFIX,
        },
        requirement_summary=session.requirement_summary,
        client_request_id=marker,
        started_at=created_at if status != "queued" else None,
        finished_at=finished_at,
        created_at=created_at,
        updated_at=finished_at or created_at,
    )
    db.add(batch)
    db.flush()
    print(
        f"[种子] 新建批次 {marker}（batch_id={batch.id}, {batch_type}/{status}）"
    )
    return batch


def _image_paths(
    *, user_id: int, session_id: int, batch_id: int, index_no: int, attempt_no: int
) -> tuple[str, str]:
    file_path = (
        f"generated/{user_id}/{session_id}/{batch_id}/{index_no}_{attempt_no}.png"
    )
    thumbnail_path = f"thumbnails/{user_id}/{batch_id}/{index_no}_{attempt_no}.webp"
    return file_path, thumbnail_path


def _write_image_files(
    *,
    batch: GenerationBatch,
    index_no: int,
    attempt_no: int,
    image_role: str,
    image_type: str,
    archived: bool,
) -> tuple[str, str]:
    """生成占位 PNG 与缩略图；归档图额外写入 archive/ 前缀。"""
    file_path, thumbnail_path = _image_paths(
        user_id=batch.user_id,
        session_id=batch.session_id,
        batch_id=batch.id,
        index_no=index_no,
        attempt_no=attempt_no,
    )
    role_label = "主图" if image_role == "main" else "详情图"
    png = render_placeholder_png(
        product_name=batch.product_name,
        role_label=role_label,
        index_no=index_no,
        batch_id=batch.id,
        width=batch.width,
        height=batch.height,
        image_type=image_type,
    )
    storage.save(file_path, png)
    storage.save(thumbnail_path, make_thumbnail_webp(png))
    if archived:
        storage.save(f"archive/{file_path}", png)
    return file_path, thumbnail_path


def _ensure_image(
    db: Session,
    *,
    batch: GenerationBatch,
    index_no: int,
    attempt_no: int = 1,
    image_type: str,
    image_role: str,
    status: str,
    is_history_visible: bool,
    created_at: datetime,
    archived: bool = False,
    error_message: str | None = None,
    prompt: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    latency_ms: int | None = None,
) -> GeneratedImage:
    existing = db.scalar(
        select(GeneratedImage).where(
            GeneratedImage.batch_id == batch.id,
            GeneratedImage.index_no == index_no,
            GeneratedImage.attempt_no == attempt_no,
        )
    )
    if existing is not None:
        # 已存在时只补齐缺失文件，不覆盖元数据
        if existing.file_path and not storage.exists(existing.file_path):
            _write_image_files(
                batch=batch,
                index_no=index_no,
                attempt_no=attempt_no,
                image_role=image_role,
                image_type=image_type,
                archived=archived,
            )
        return existing

    file_path: str | None = None
    thumbnail_path: str | None = None
    archived_at: datetime | None = None
    # superseded 旧图曾成功生成过，保留文件与缩略图便于追溯
    if status in ("success", "superseded"):
        file_path, thumbnail_path = _write_image_files(
            batch=batch,
            index_no=index_no,
            attempt_no=attempt_no,
            image_role=image_role,
            image_type=image_type,
            archived=archived,
        )
        if archived and status == "success":
            archived_at = created_at

    image = GeneratedImage(
        batch_id=batch.id,
        user_id=batch.user_id,
        session_id=batch.session_id,
        image_type=image_type,
        image_role=image_role,
        index_no=index_no,
        attempt_no=attempt_no,
        status=status,
        source_image_id=None,
        file_path=file_path,
        thumbnail_path=thumbnail_path,
        width=batch.width if file_path else None,
        height=batch.height if file_path else None,
        prompt=prompt,
        negative_prompt=None,
        model_name=IMAGE_MODEL if file_path else None,
        latency_ms=latency_ms if file_path else None,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        error_message=error_message,
        is_history_visible=is_history_visible,
        archived_at=archived_at,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(image)
    db.flush()
    return image


def _ensure_agent_run(
    db: Session,
    *,
    marker: str,
    session: CreativeSession,
    agent_code: str,
    status: str,
    model_name: str | None,
    created_at: datetime,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    batch: GenerationBatch | None = None,
    error_message: str | None = None,
) -> AgentRun:
    existing = db.scalar(select(AgentRun).where(AgentRun.input_summary == marker))
    if existing is not None:
        return existing

    run = AgentRun(
        session_id=session.id,
        message_id=None,
        batch_id=batch.id if batch else None,
        image_id=None,
        agent_code=agent_code,
        status=status,
        model_name=model_name,
        input_summary=marker,
        output_summary=f"{AGENT_NAMES.get(agent_code, agent_code)} 演示输出",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        error_message=error_message,
        created_at=created_at,
    )
    db.add(run)
    db.flush()
    return run


def _seed_content(db: Session, base_date) -> None:
    """写入四个演示用户的内容链路。"""
    user_a = _get_user(db, "demo_user")
    user_b = _get_user(db, "demo_user2")
    user_super = _get_user(db, "demo_super")

    # 会话：demo_user 1 活跃 + 1 隐藏；demo_user2、demo_super 各 1 个
    session_a = _ensure_session(
        db,
        user=user_a,
        title="秋季通勤衬衫",
        status="active",
        created_at=_at(base_date, 6, 9, 0),
        last_message_at=_at(base_date, 0, 9, 30),
        product_name="秋季通勤衬衫",
    )
    session_hidden = _ensure_session(
        db,
        user=user_a,
        title="夏季连衣裙（已隐藏）",
        status="hidden",
        created_at=_at(base_date, 5, 9, 0),
        last_message_at=_at(base_date, 0, 10, 0),
        product_name="夏季连衣裙",
    )
    session_b = _ensure_session(
        db,
        user=user_b,
        title="保温杯套装",
        status="active",
        created_at=_at(base_date, 1, 9, 0),
        last_message_at=_at(base_date, 1, 11, 0),
        product_name="保温杯套装",
    )
    session_super = _ensure_session(
        db,
        user=user_super,
        title="超管测试商品",
        status="active",
        created_at=_at(base_date, 0, 8, 0),
        last_message_at=_at(base_date, 0, 8, 30),
        product_name="超管测试商品",
    )

    # demo_user 活跃会话：示例待确认、完成、部分失败、取消、失败示例
    sample_ready = _ensure_batch(
        db,
        user=user_a,
        session=session_a,
        batch_type="sample",
        status="sample_ready",
        product_name="秋季通勤衬衫",
        style_text="简洁白底",
        width=1000,
        height=1000,
        total_count=1,
        completed_count=1,
        created_at=_at(base_date, 6, 10, 0),
        marker=f"{SEED_PREFIX}:batch:sample-ready",
    )
    completed = _ensure_batch(
        db,
        user=user_a,
        session=session_a,
        batch_type="full",
        status="completed",
        product_name="秋季通勤衬衫",
        style_text="简洁白底",
        width=1000,
        height=1000,
        total_count=6,
        completed_count=6,
        source_sample_batch_id=sample_ready.id,
        created_at=_at(base_date, 5, 10, 0),
        marker=f"{SEED_PREFIX}:batch:completed",
    )
    partially_failed = _ensure_batch(
        db,
        user=user_a,
        session=session_a,
        batch_type="full",
        status="partially_failed",
        product_name="秋季通勤衬衫",
        style_text="生活场景",
        width=1000,
        height=1000,
        total_count=6,
        completed_count=4,
        source_sample_batch_id=sample_ready.id,
        created_at=_at(base_date, 4, 10, 0),
        marker=f"{SEED_PREFIX}:batch:partially-failed",
    )
    cancelled = _ensure_batch(
        db,
        user=user_a,
        session=session_a,
        batch_type="full",
        status="cancelled",
        product_name="秋季通勤衬衫",
        style_text="国潮",
        width=1000,
        height=1000,
        total_count=6,
        completed_count=2,
        source_sample_batch_id=sample_ready.id,
        created_at=_at(base_date, 3, 10, 0),
        marker=f"{SEED_PREFIX}:batch:cancelled",
    )
    failed_sample = _ensure_batch(
        db,
        user=user_a,
        session=session_a,
        batch_type="sample",
        status="failed",
        product_name="秋季通勤衬衫",
        style_text=None,
        width=1000,
        height=1000,
        total_count=1,
        completed_count=0,
        created_at=_at(base_date, 2, 10, 0),
        marker=f"{SEED_PREFIX}:batch:failed-sample",
    )

    # demo_user 隐藏会话：归档完成批次（今天创建，满足今日统计）
    archived_batch = _ensure_batch(
        db,
        user=user_a,
        session=session_hidden,
        batch_type="full",
        status="completed",
        product_name="夏季连衣裙",
        style_text="清新浅色",
        width=1000,
        height=1000,
        total_count=6,
        completed_count=6,
        source_sample_batch_id=sample_ready.id,
        created_at=_at(base_date, ARCHIVE_DAY_OFFSET, 9, 0),
        marker=f"{SEED_PREFIX}:batch:archived",
    )

    # demo_user2：部分失败 + 排队（覆盖 6 种批次状态）
    partial_b = _ensure_batch(
        db,
        user=user_b,
        session=session_b,
        batch_type="sample",
        status="partially_failed",
        product_name="保温杯套装",
        style_text="高级质感",
        width=800,
        height=800,
        total_count=1,
        completed_count=0,
        created_at=_at(base_date, 1, 10, 0),
        marker=f"{SEED_PREFIX}:batch:user2-partial",
    )
    queued_b = _ensure_batch(
        db,
        user=user_b,
        session=session_b,
        batch_type="sample",
        status="queued",
        product_name="保温杯套装",
        style_text="高级质感",
        width=800,
        height=800,
        total_count=1,
        completed_count=0,
        created_at=_at(base_date, 0, 11, 0),
        marker=f"{SEED_PREFIX}:batch:user2-queued",
    )

    # demo_super：完成批次，用于验证管理员过滤
    completed_super = _ensure_batch(
        db,
        user=user_super,
        session=session_super,
        batch_type="sample",
        status="completed",
        product_name="超管测试商品",
        style_text="简洁白底",
        width=1000,
        height=1000,
        total_count=1,
        completed_count=1,
        created_at=_at(base_date, 0, 8, 10),
        marker=f"{SEED_PREFIX}:batch:super-completed",
    )

    # ---------------- 图片 ----------------
    # 示例待确认：1 张示例主图
    _ensure_image(
        db,
        batch=sample_ready,
        index_no=1,
        image_type="sample",
        image_role="main",
        status="success",
        is_history_visible=False,
        created_at=sample_ready.created_at + timedelta(minutes=1),
        prompt="白底商品主图，突出面料质感",
        prompt_tokens=120,
        completion_tokens=0,
        latency_ms=9000,
    )

    # 完成全套：1 主图 + 5 详情图
    for index_no in range(1, 7):
        role = "main" if index_no == 1 else "detail"
        _ensure_image(
            db,
            batch=completed,
            index_no=index_no,
            image_type="final",
            image_role=role,
            status="success",
            is_history_visible=True,
            created_at=completed.created_at + timedelta(minutes=index_no),
            prompt=f"秋季通勤衬衫{'主图' if index_no == 1 else '详情图'}，简洁白底",
            prompt_tokens=100,
            completion_tokens=0,
            latency_ms=11000 + index_no * 100,
        )

    # 部分失败：4 张成功 + 2 张失败；第 3 张含被替代的旧尝试
    partial_images = [
        (1, "main", "success", 1, False, None),
        (2, "detail", "success", 1, False, None),
        (3, "detail", "superseded", 1, False, None),
        (3, "detail", "success", 2, False, None),
        (4, "detail", "success", 1, False, None),
        (5, "detail", "failed", 1, False, "生图服务超时"),
        (6, "detail", "failed", 1, False, "内容审核未通过"),
    ]
    for index_no, role, status, attempt, archived, error in partial_images:
        _ensure_image(
            db,
            batch=partially_failed,
            index_no=index_no,
            attempt_no=attempt,
            image_type="final",
            image_role=role,
            status=status,
            is_history_visible=status == "success",
            created_at=partially_failed.created_at
            + timedelta(minutes=index_no, seconds=attempt),
            error_message=error,
            prompt="秋季通勤衬衫详情图，生活场景",
            prompt_tokens=90 if status != "superseded" else 80,
            completion_tokens=0,
            latency_ms=12000,
        )

    # 取消全套：2 张成功，其余取消/待生成
    _ensure_image(
        db,
        batch=cancelled,
        index_no=1,
        image_type="final",
        image_role="main",
        status="success",
        is_history_visible=True,
        created_at=cancelled.created_at + timedelta(minutes=1),
        prompt="秋季通勤衬衫主图，国潮风",
        prompt_tokens=95,
        latency_ms=10000,
    )
    _ensure_image(
        db,
        batch=cancelled,
        index_no=2,
        image_type="final",
        image_role="detail",
        status="success",
        is_history_visible=True,
        created_at=cancelled.created_at + timedelta(minutes=2),
        prompt="秋季通勤衬衫详情图，国潮风",
        prompt_tokens=95,
        latency_ms=10000,
    )
    _ensure_image(
        db,
        batch=cancelled,
        index_no=3,
        image_type="final",
        image_role="detail",
        status="cancelled",
        is_history_visible=False,
        created_at=cancelled.created_at + timedelta(minutes=3),
        error_message="用户取消生成",
    )
    for index_no in range(4, 7):
        _ensure_image(
            db,
            batch=cancelled,
            index_no=index_no,
            image_type="final",
            image_role="detail",
            status="pending",
            is_history_visible=False,
            created_at=cancelled.created_at + timedelta(minutes=index_no),
        )

    # 失败示例：无文件
    _ensure_image(
        db,
        batch=failed_sample,
        index_no=1,
        image_type="sample",
        image_role="main",
        status="failed",
        is_history_visible=False,
        created_at=failed_sample.created_at + timedelta(minutes=1),
        error_message="模型返回内容审核未通过",
        prompt="秋季通勤衬衫示例主图",
    )

    # 归档完成批次：6 张成功，第 4 张为归档原件
    for index_no in range(1, 7):
        role = "main" if index_no == 1 else "detail"
        _ensure_image(
            db,
            batch=archived_batch,
            index_no=index_no,
            image_type="final",
            image_role=role,
            status="success",
            is_history_visible=True,
            created_at=archived_batch.created_at + timedelta(minutes=index_no),
            archived=index_no == 4,
            prompt=f"夏季连衣裙{'主图' if index_no == 1 else '详情图'}，清新浅色",
            prompt_tokens=110,
            latency_ms=10500,
        )

    # demo_user2 部分失败与排队
    _ensure_image(
        db,
        batch=partial_b,
        index_no=1,
        image_type="sample",
        image_role="main",
        status="failed",
        is_history_visible=False,
        created_at=partial_b.created_at + timedelta(minutes=1),
        error_message="生图服务不可用",
    )
    _ensure_image(
        db,
        batch=queued_b,
        index_no=1,
        image_type="sample",
        image_role="main",
        status="pending",
        is_history_visible=False,
        created_at=queued_b.created_at + timedelta(minutes=1),
    )

    # demo_super 完成示例
    _ensure_image(
        db,
        batch=completed_super,
        index_no=1,
        image_type="sample",
        image_role="main",
        status="success",
        is_history_visible=False,
        created_at=completed_super.created_at + timedelta(minutes=1),
        prompt="超管测试商品示例主图",
        prompt_tokens=88,
        latency_ms=9800,
    )

    # ---------------- Agent 调用 ----------------
    # 8 个 Agent 跨 7 个自然日，覆盖 2 个模型名与 success
    for index, agent_code in enumerate(AGENT_NAMES):
        day_offset = index % 7
        model = IMAGE_MODEL if agent_code == "image_generator" else TEXT_MODEL
        batch = completed if day_offset == 5 else sample_ready
        _ensure_agent_run(
            db,
            marker=f"{SEED_PREFIX}:run:{agent_code}:{day_offset}",
            session=session_a,
            agent_code=agent_code,
            status="success",
            model_name=model,
            created_at=_at(base_date, day_offset, 12, index),
            prompt_tokens=100 + index * 10,
            completion_tokens=50 + index * 5,
            latency_ms=1200 + index * 100,
            batch=batch,
        )

    # 失败但有 Token：计入统计
    _ensure_agent_run(
        db,
        marker=f"{SEED_PREFIX}:run:failed-with-tokens",
        session=session_a,
        agent_code="copywriter",
        status="failed",
        model_name=TEXT_MODEL,
        created_at=_at(base_date, 0, 13, 0),
        prompt_tokens=10,
        completion_tokens=20,
        latency_ms=800,
        batch=completed,
        error_message="模型响应超时",
    )
    # 失败且 0 Token：不计入
    _ensure_agent_run(
        db,
        marker=f"{SEED_PREFIX}:run:failed-zero",
        session=session_a,
        agent_code="repairer",
        status="failed",
        model_name=TEXT_MODEL,
        created_at=_at(base_date, 0, 13, 5),
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=500,
        batch=completed,
        error_message="调用前校验失败",
    )
    # 跳过：0 Token，不计入
    _ensure_agent_run(
        db,
        marker=f"{SEED_PREFIX}:run:skipped-zero",
        session=session_a,
        agent_code="platform_rule",
        status="skipped",
        model_name=None,
        created_at=_at(base_date, 2, 13, 10),
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=0,
        batch=partially_failed,
    )
    # 其他用户各一条成功调用，便于用户统计交叉核对
    _ensure_agent_run(
        db,
        marker=f"{SEED_PREFIX}:run:user2-success",
        session=session_b,
        agent_code="planner",
        status="success",
        model_name=TEXT_MODEL,
        created_at=_at(base_date, 1, 12, 0),
        prompt_tokens=30,
        completion_tokens=40,
        latency_ms=700,
        batch=partial_b,
    )
    _ensure_agent_run(
        db,
        marker=f"{SEED_PREFIX}:run:super-success",
        session=session_super,
        agent_code="planner",
        status="success",
        model_name=TEXT_MODEL,
        created_at=_at(base_date, 0, 8, 40),
        prompt_tokens=70,
        completion_tokens=80,
        latency_ms=750,
        batch=completed_super,
    )


def seed_admin(db: Session) -> None:
    """执行 7 号幂等种子；依赖 auth 种子已创建演示账号。"""
    base_date = datetime.now(settings.TZ).date()
    print("[种子] 开始写入 7 号管理后台演示数据……")
    _seed_content(db, base_date)
    db.commit()
    print("[种子] 7 号管理后台演示数据完成。")
