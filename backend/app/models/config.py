"""配置域 ORM 模型（模板、素材、模型配置、系统提示词、尺寸预设）。

字段与约束对齐 docs/prd/10-数据模型与存储prd.md §4.12~§4.16、§4.18。
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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Template(Base):
    """模板 templates。"""

    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    style_text: Mapped[str | None] = mapped_column(String(50), nullable=True)
    thumbnail_path: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    layout_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('active','disabled')", name="ck_templates_status"),
        Index("idx_templates_status_sort", "status", "sort_order"),
    )


class MaterialAsset(Base):
    """素材库 material_assets。"""

    __tablename__ = "material_assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    style_tags: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("status IN ('active','disabled')", name="ck_materials_status"),
        Index("idx_materials_status_sort", "status", "sort_order"),
        Index("idx_materials_tags", "tags", postgresql_using="gin"),
    )


class ModelConfig(Base):
    """模型配置 model_configs。"""

    __tablename__ = "model_configs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'volcengine_ark'"))
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_model: Mapped[str] = mapped_column(String(100), nullable=False)
    image_model: Mapped[str] = mapped_column(String(100), nullable=False)
    vision_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    temperature: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False, server_default=text("0.7"))
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("120"))
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("4"))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    max_context_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("temperature BETWEEN 0 AND 2", name="ck_model_temperature"),
        CheckConstraint("timeout_seconds BETWEEN 30 AND 300", name="ck_model_timeout"),
        CheckConstraint("concurrency BETWEEN 1 AND 16", name="ck_model_concurrency"),
        CheckConstraint("retry_count BETWEEN 0 AND 3", name="ck_model_retry"),
        Index(
            "uq_model_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )


class SystemPrompt(Base):
    """系统提示词 system_prompts。"""

    __tablename__ = "system_prompts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("agent_code", name="uq_prompts_agent_code"),
    )


class PromptVersion(Base):
    """提示词版本 prompt_versions。"""

    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prompt_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("system_prompts.id", ondelete="RESTRICT"), nullable=False
    )
    agent_code: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("prompt_id", "version", name="uq_prompt_versions"),
        Index("idx_prompt_versions_prompt", "prompt_id", "version"),
    )


class SizePreset(Base):
    """尺寸预设 size_presets。"""

    __tablename__ = "size_presets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    platform_name: Mapped[str] = mapped_column(String(50), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'active'"))
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("width > 0 AND height > 0", name="ck_sizes_positive"),
        CheckConstraint("status IN ('active','disabled')", name="ck_sizes_status"),
        UniqueConstraint("platform_name", "width", "height", name="uq_sizes_platform_size"),
        Index("idx_sizes_status_sort", "status", "sort_order"),
    )
