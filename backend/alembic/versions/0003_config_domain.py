"""配置域六表：templates、material_assets、model_configs、system_prompts、prompt_versions、size_presets

Revision ID: 0003_config_domain
Revises: 0002_content_domain
Create Date: 2026-10-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_config_domain"
down_revision = "0002_content_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "templates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("style_text", sa.String(length=50), nullable=True),
        sa.Column("thumbnail_path", sa.Text(), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=True),
        sa.Column("layout_ref", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_templates_status"),
    )
    op.create_index("idx_templates_status_sort", "templates", ["status", "sort_order"])

    op.create_table(
        "material_assets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("style_tags", postgresql.JSONB(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_materials_status"),
    )
    op.create_index("idx_materials_status_sort", "material_assets", ["status", "sort_order"])
    op.create_index("idx_materials_tags", "material_assets", ["tags"], postgresql_using="gin")

    op.create_table(
        "model_configs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default=sa.text("'volcengine_ark'")),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("text_model", sa.String(length=100), nullable=False),
        sa.Column("image_model", sa.String(length=100), nullable=False),
        sa.Column("vision_model", sa.String(length=100), nullable=True),
        sa.Column("temperature", sa.Numeric(3, 1), nullable=False, server_default=sa.text("0.7")),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default=sa.text("120")),
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default=sa.text("4")),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("max_context_tokens", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("temperature BETWEEN 0 AND 2", name="ck_model_temperature"),
        sa.CheckConstraint("timeout_seconds BETWEEN 30 AND 300", name="ck_model_timeout"),
        sa.CheckConstraint("concurrency BETWEEN 1 AND 16", name="ck_model_concurrency"),
        sa.CheckConstraint("retry_count BETWEEN 0 AND 3", name="ck_model_retry"),
    )
    op.create_index(
        "uq_model_active", "model_configs", ["is_active"],
        unique=True, postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "system_prompts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("agent_code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("agent_code", name="uq_prompts_agent_code"),
    )

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("prompt_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_code", sa.String(length=40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("prompt_id", "version", name="uq_prompt_versions"),
        sa.ForeignKeyConstraint(["prompt_id"], ["system_prompts.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_prompt_versions_prompt", "prompt_versions", ["prompt_id", "version"])

    op.create_table(
        "size_presets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("platform_name", sa.String(length=50), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_sizes_positive"),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_sizes_status"),
        sa.UniqueConstraint("platform_name", "width", "height", name="uq_sizes_platform_size"),
    )
    op.create_index("idx_sizes_status_sort", "size_presets", ["status", "sort_order"])


def downgrade() -> None:
    op.drop_index("idx_sizes_status_sort", table_name="size_presets")
    op.drop_table("size_presets")
    op.drop_index("idx_prompt_versions_prompt", table_name="prompt_versions")
    op.drop_table("prompt_versions")
    op.drop_table("system_prompts")
    op.drop_index("uq_model_active", table_name="model_configs")
    op.drop_table("model_configs")
    op.drop_index("idx_materials_tags", table_name="material_assets")
    op.drop_index("idx_materials_status_sort", table_name="material_assets")
    op.drop_table("material_assets")
    op.drop_index("idx_templates_status_sort", table_name="templates")
    op.drop_table("templates")
