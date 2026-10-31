"""创作工作台相关 ORM 模型。

字段、默认值与约束对齐 docs/prd/10-数据模型与存储prd.md §4.6~§4.11。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CreativeSession(Base):
    """创作会话 creative_sessions。"""

    __tablename__ = "creative_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    requirement_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('active','hidden')", name="ck_sessions_status"),
        Index("idx_sessions_user_status_time", "user_id", "status", "last_message_at"),
        Index("idx_sessions_last_message_at", "last_message_at"),
    )


class ChatMessage(Base):
    """聊天消息 chat_messages。"""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("creative_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    agent_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'text'")
    )
    client_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_in: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    token_out: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'done'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system')", name="ck_messages_role"),
        CheckConstraint("status IN ('sending','done','failed')", name="ck_messages_status"),
        Index(
            "uq_messages_session_client",
            "session_id",
            "client_message_id",
            unique=True,
            postgresql_where=text("client_message_id IS NOT NULL"),
        ),
        Index("idx_messages_session_time", "session_id", "created_at"),
        Index("idx_messages_created_at", "created_at"),
    )


class AgentRun(Base):
    """Agent 调用记录 agent_runs。"""

    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("creative_sessions.id", ondelete="RESTRICT"), nullable=True
    )
    message_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chat_messages.id", ondelete="RESTRICT"), nullable=True
    )
    batch_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("generation_batches.id", ondelete="RESTRICT"), nullable=True
    )
    image_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("generated_images.id", ondelete="RESTRICT"), nullable=True
    )
    agent_code: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_full: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_full: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('success','failed','skipped')", name="ck_agent_runs_status"),
        Index("idx_agent_runs_session", "session_id", "created_at"),
        Index("idx_agent_runs_batch", "batch_id", "created_at"),
        Index("idx_agent_runs_image", "image_id"),
        Index("idx_agent_runs_agent_time", "agent_code", "created_at"),
        Index("idx_agent_runs_created_at", "created_at"),
    )


class GenerationBatch(Base):
    """生成批次 generation_batches。"""

    __tablename__ = "generation_batches"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("creative_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    batch_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_sample_batch_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    product_name: Mapped[str] = mapped_column(String(60), nullable=False)
    style_text: Mapped[str | None] = mapped_column(String(50), nullable=True)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    template_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'queued'"))
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    params_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    requirement_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("batch_type IN ('sample','full')", name="ck_batches_type"),
        CheckConstraint(
            "status IN ('queued','running','sample_ready','confirmed','completed',"
            "'partially_failed','failed','cancelled')",
            name="ck_batches_status",
        ),
        CheckConstraint(
            "stage IS NULL OR stage IN ('planner','product_understanding','copywriter',"
            "'prompt_builder','image_generator','quality_reviewer','repairer','platform_rule',"
            "'text_composition','done')",
            name="ck_batches_stage",
        ),
        CheckConstraint(
            "(batch_type = 'full' AND source_sample_batch_id IS NOT NULL) OR "
            "(batch_type = 'sample' AND source_sample_batch_id IS NULL)",
            name="ck_batches_source",
        ),
        Index(
            "uq_batches_client_request",
            "client_request_id",
            unique=True,
            postgresql_where=text("client_request_id IS NOT NULL"),
        ),
        Index("idx_batches_user_time", "user_id", "created_at"),
        Index("idx_batches_session_time", "session_id", "created_at"),
        Index("idx_batches_status", "status"),
        Index("idx_batches_type", "batch_type"),
    )


class GeneratedImage(Base):
    """生成图片 generated_images。"""

    __tablename__ = "generated_images"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("generation_batches.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("creative_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    image_type: Mapped[str] = mapped_column(String(16), nullable=False)
    image_role: Mapped[str] = mapped_column(String(16), nullable=False)
    index_no: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    # 单张重试/重生成幂等键（4 号 demo 增量字段，10 号文档未列出，仅内部使用）
    client_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_image_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_history_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("image_type IN ('sample','final')", name="ck_images_type"),
        CheckConstraint("image_role IN ('main','detail')", name="ck_images_role"),
        CheckConstraint(
            "status IN ('pending','generating','success','failed','cancelled','superseded')",
            name="ck_images_status",
        ),
        Index("idx_images_batch_index", "batch_id", "index_no", "attempt_no"),
        Index("idx_images_user_history", "user_id", "is_history_visible", "created_at"),
        Index("idx_images_status", "status"),
        Index("idx_images_archived_at", "archived_at"),
        Index(
            "uq_images_client_request",
            "client_request_id",
            unique=True,
            postgresql_where=text("client_request_id IS NOT NULL"),
        ),
    )


class UploadedAsset(Base):
    """用户上传商品图 uploaded_assets。"""

    __tablename__ = "uploaded_assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("creative_sessions.id", ondelete="RESTRICT"), nullable=True
    )
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('active','deleted')", name="ck_uploads_status"),
        Index("idx_uploads_user_session", "user_id", "session_id", "sort_order"),
        Index("idx_uploads_status", "status"),
        Index("idx_uploads_archived_at", "archived_at"),
    )
