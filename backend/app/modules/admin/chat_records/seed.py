"""8 号管理后台-聊天记录：幂等演示种子。

按接口文档 §2.3 写入 4 个会话及其消息、Agent 调用与生成批次：
- demo_user：秋季通勤衬衫（active，12 消息 / 6 调用 / 2 批次）
- demo_user：夏季防晒外套（hidden，6 消息 / 2 调用 / 1 批次）
- demo_user：通勤鞋搭配建议（active，4 消息 / 2 调用 / 0 批次）
- demo_super：超管测试会话（active，2 消息 / 1 调用 / 0 批次）

以 ``(user_id, title)`` 识别会话；会话已存在时跳过其全部子数据，不覆盖。
所有 ``input_full`` / ``output_full`` 均为已脱敏的演示文本。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workspace import AgentRun, ChatMessage, CreativeSession, GenerationBatch

MODEL_NAME = "doubao-seed-character-demo"
REDACTED_INPUT = '{"product_name":"秋季通勤衬衫","api_key":"[REDACTED]","note":"演示数据"}'
REDACTED_OUTPUT = '{"plan":"主图 1 张 + 详情图 5 张","authorization":"[REDACTED]"}'

# (role, agent_code, content, token_in, token_out)
MessageSpec = tuple[str, str | None, str, int, int]


def _at(now: datetime, minutes_ago: int) -> datetime:
    return now - timedelta(minutes=minutes_ago)


def _create_batches(
    db: Session,
    *,
    user_id: int,
    session_id: int,
    product_name: str,
    now: datetime,
    sample_only: bool,
) -> dict[str, GenerationBatch]:
    """写入示例批次；需要时再写全套批次，返回按类型索引的批次。"""
    sample = GenerationBatch(
        user_id=user_id,
        session_id=session_id,
        batch_type="sample",
        source_sample_batch_id=None,
        product_name=product_name,
        style_text="简洁白底",
        width=1000,
        height=1000,
        template_name=None,
        total_count=6,
        completed_count=6,
        status="completed",
        stage="done",
        params_snapshot={"product_name": product_name, "width": 1000, "height": 1000},
        created_at=_at(now, 180),
        started_at=_at(now, 180),
        finished_at=_at(now, 170),
    )
    db.add(sample)
    db.flush()
    batches = {"sample": sample}
    if sample_only:
        return batches

    full = GenerationBatch(
        user_id=user_id,
        session_id=session_id,
        batch_type="full",
        source_sample_batch_id=sample.id,
        product_name=product_name,
        style_text="简洁白底",
        width=1000,
        height=1000,
        template_name=None,
        total_count=6,
        completed_count=6,
        status="completed",
        stage="done",
        params_snapshot={"product_name": product_name, "width": 1000, "height": 1000},
        created_at=_at(now, 120),
        started_at=_at(now, 120),
        finished_at=_at(now, 110),
    )
    db.add(full)
    db.flush()
    batches["full"] = full
    return batches


def _create_session(
    db: Session,
    *,
    user: User,
    title: str,
    status: str,
    messages: list[MessageSpec],
    runs: list[dict],
    now: datetime,
    last_message_minutes_ago: int,
    sample_only: bool = False,
    with_batches: bool = True,
) -> bool:
    """写入一个会话；已存在时跳过并返回 False。"""
    existing = db.scalar(
        select(CreativeSession).where(
            CreativeSession.user_id == user.id,
            CreativeSession.title == title,
        )
    )
    if existing is not None:
        print(f"[种子] 会话「{title}」已存在，跳过")
        return False

    session = CreativeSession(
        user_id=user.id,
        title=title,
        status=status,
        requirement_summary={"product_name": title},
        last_message_at=_at(now, last_message_minutes_ago),
        created_at=_at(now, last_message_minutes_ago + 240),
    )
    db.add(session)
    db.flush()

    batches = (
        _create_batches(
            db,
            user_id=user.id,
            session_id=session.id,
            product_name=title,
            now=now,
            sample_only=sample_only,
        )
        if with_batches
        else {}
    )

    message_ids: list[int] = []
    total = len(messages)
    for index, (role, agent_code, content, token_in, token_out) in enumerate(messages):
        message = ChatMessage(
            session_id=session.id,
            role=role,
            agent_code=agent_code,
            content=content,
            content_type="markdown" if role == "assistant" else "text",
            client_message_id=None,
            token_in=token_in,
            token_out=token_out,
            status="done",
            created_at=_at(now, last_message_minutes_ago + (total - 1 - index) * 3),
        )
        db.add(message)
        db.flush()
        message_ids.append(message.id)

    for run_spec in runs:
        batch_type = run_spec.get("batch_type")
        batch = batches.get(batch_type) if batch_type else None
        db.add(
            AgentRun(
                session_id=session.id,
                message_id=message_ids[run_spec["message_index"]],
                batch_id=batch.id if batch is not None else None,
                image_id=None,
                agent_code=run_spec["agent_code"],
                status=run_spec["status"],
                model_name=MODEL_NAME if run_spec["status"] != "skipped" else None,
                input_summary=run_spec.get("input_summary", "演示输入摘要"),
                output_summary=run_spec.get("output_summary", "演示输出摘要"),
                input_full=(
                    REDACTED_INPUT if run_spec["status"] != "skipped" else None
                ),
                output_full=(
                    REDACTED_OUTPUT if run_spec["status"] != "skipped" else None
                ),
                prompt_tokens=run_spec.get("prompt_tokens", 0),
                completion_tokens=run_spec.get("completion_tokens", 0),
                latency_ms=run_spec.get("latency_ms"),
                error_message=run_spec.get("error_message"),
                created_at=_at(
                    now, last_message_minutes_ago + (total - 1 - run_spec["message_index"]) * 3
                ),
            )
        )

    db.commit()
    print(f"[种子] 新增会话「{title}」：{len(messages)} 条消息 / {len(runs)} 条调用")
    return True


def seed_chat_records(db: Session) -> None:
    """幂等写入 8 号聊天记录演示夹具。"""
    now = datetime.now(timezone.utc)

    demo_user = db.scalar(select(User).where(User.username == "demo_user"))
    demo_super = db.scalar(select(User).where(User.username == "demo_super"))
    if demo_user is None or demo_super is None:
        print("[种子] 缺少 demo_user 或 demo_super，跳过聊天记录夹具")
        return

    # 1. 秋季通勤衬衫：12 消息 / 6 调用 / 2 批次
    _create_session(
        db,
        user=demo_user,
        title="秋季通勤衬衫",
        status="active",
        now=now,
        last_message_minutes_ago=120,
        messages=[
            ("user", None, "帮我做一套秋季通勤衬衫的图，风格简洁一点。", 0, 0),
            ("assistant", "planner", "好的，我先确认几个信息：商品名称、使用场景与尺寸。", 120, 300),
            ("assistant", "product_understanding", "已识别为服饰类目，卖点：通勤、百搭。", 100, 200),
            ("user", None, "背景再亮一点。", 0, 0),
            ("assistant", "copywriter", "标题：秋季通勤衬衫；卖点：通勤百搭、面料挺括。", 80, 160),
            ("system", None, "示例图已生成。", 0, 0),
            ("user", None, "T-shirt 的领口再自然一点。", 0, 0),
            ("assistant", "prompt_builder", "已更新提示词，保留文字区。", 90, 180),
            ("assistant", "image_generator", "示例图生成完成。", 50, 0),
            ("assistant", "quality_reviewer", "审核通过。", 40, 20),
            ("assistant", "repairer", "本轮无需修复。", 0, 0),
            ("system", None, "全套图已生成。", 0, 0),
        ],
        runs=[
            {
                "message_index": 1,
                "agent_code": "planner",
                "status": "success",
                "prompt_tokens": 120,
                "completion_tokens": 300,
                "latency_ms": 820,
                "input_summary": "商品名称：秋季通勤衬衫；风格：简洁……",
                "output_summary": "任务计划：主图 1 张、详情图 5 张……",
            },
            {
                "message_index": 2,
                "agent_code": "product_understanding",
                "status": "success",
                "prompt_tokens": 100,
                "completion_tokens": 200,
                "latency_ms": 640,
            },
            {
                "message_index": 4,
                "agent_code": "copywriter",
                "status": "success",
                "prompt_tokens": 80,
                "completion_tokens": 160,
                "latency_ms": 510,
                "batch_type": "sample",
            },
            {
                "message_index": 7,
                "agent_code": "prompt_builder",
                "status": "failed",
                "prompt_tokens": 90,
                "completion_tokens": 0,
                "latency_ms": 30000,
                "error_message": "上游模型超时",
            },
            {
                "message_index": 8,
                "agent_code": "image_generator",
                "status": "success",
                "prompt_tokens": 50,
                "completion_tokens": 0,
                "latency_ms": 1250,
                "batch_type": "sample",
            },
            {
                "message_index": 9,
                "agent_code": "quality_reviewer",
                "status": "skipped",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "latency_ms": None,
                "output_summary": "视觉模型未配置，本轮跳过质量审核。",
            },
        ],
    )

    # 2. 夏季防晒外套：hidden，6 消息 / 2 调用 / 1 批次
    _create_session(
        db,
        user=demo_user,
        title="夏季防晒外套",
        status="hidden",
        now=now,
        last_message_minutes_ago=1440,
        sample_only=True,
        messages=[
            ("user", None, "夏季防晒外套，想要清凉一点的背景。", 0, 0),
            ("assistant", "planner", "已拆解为 1 张主图 + 5 张详情图。", 60, 120),
            ("assistant", "product_understanding", "识别为户外服饰类目。", 50, 100),
            ("user", None, "可以。", 0, 0),
            ("assistant", "copywriter", "标题：轻薄防晒外套。", 40, 80),
            ("system", None, "示例图已生成。", 0, 0),
        ],
        runs=[
            {
                "message_index": 1,
                "agent_code": "planner",
                "status": "success",
                "prompt_tokens": 60,
                "completion_tokens": 120,
                "latency_ms": 700,
            },
            {
                "message_index": 2,
                "agent_code": "product_understanding",
                "status": "success",
                "prompt_tokens": 50,
                "completion_tokens": 100,
                "latency_ms": 620,
                "batch_type": "sample",
            },
        ],
    )

    # 3. 通勤鞋搭配建议：active，4 消息 / 2 调用 / 0 批次
    _create_session(
        db,
        user=demo_user,
        title="通勤鞋搭配建议",
        status="active",
        now=now,
        last_message_minutes_ago=180,
        with_batches=False,
        messages=[
            ("user", None, "通勤鞋怎么搭配衬衫？", 0, 0),
            ("assistant", "planner", "建议浅色系搭配，保持整体简洁。", 30, 60),
            ("assistant", "copywriter", "文案方向：轻通勤、低饱和。", 20, 40),
            ("system", None, "仅提供搭配建议，未生成图片。", 0, 0),
        ],
        runs=[
            {
                "message_index": 1,
                "agent_code": "planner",
                "status": "success",
                "prompt_tokens": 30,
                "completion_tokens": 60,
                "latency_ms": 400,
            },
            {
                "message_index": 2,
                "agent_code": "copywriter",
                "status": "success",
                "prompt_tokens": 20,
                "completion_tokens": 40,
                "latency_ms": 380,
            },
        ],
    )

    # 4. 超管测试会话：active，2 消息 / 1 调用 / 0 批次
    _create_session(
        db,
        user=demo_super,
        title="超管测试会话",
        status="active",
        now=now,
        last_message_minutes_ago=30,
        with_batches=False,
        messages=[
            ("user", None, "这是超管测试会话，用于验证可见范围。", 0, 0),
            ("assistant", "planner", "已记录超管测试消息。", 10, 20),
        ],
        runs=[
            {
                "message_index": 1,
                "agent_code": "planner",
                "status": "success",
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "latency_ms": 200,
            },
        ],
    )
