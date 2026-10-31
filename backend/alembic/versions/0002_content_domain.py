"""内容域六表：creative_sessions、chat_messages、generation_batches、generated_images、agent_runs、uploaded_assets

Revision ID: 0002_content_domain
Revises: 0001_identity_and_audit
Create Date: 2026-10-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_content_domain"
down_revision = "0001_identity_and_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "creative_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("requirement_summary", postgresql.JSONB(), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active','hidden')", name="ck_sessions_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_sessions_user_status_time", "creative_sessions", ["user_id", "status", "last_message_at"])
    op.create_index("idx_sessions_last_message_at", "creative_sessions", ["last_message_at"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("agent_code", sa.String(length=40), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=16), nullable=False, server_default=sa.text("'text'")),
        sa.Column("client_message_id", sa.String(length=64), nullable=True),
        sa.Column("token_in", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("token_out", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'done'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('user','assistant','system')", name="ck_messages_role"),
        sa.CheckConstraint("status IN ('sending','done','failed')", name="ck_messages_status"),
        sa.ForeignKeyConstraint(["session_id"], ["creative_sessions.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_messages_session_client", "chat_messages", ["session_id", "client_message_id"],
        unique=True, postgresql_where=sa.text("client_message_id IS NOT NULL"),
    )
    op.create_index("idx_messages_session_time", "chat_messages", ["session_id", "created_at"])
    op.create_index("idx_messages_created_at", "chat_messages", ["created_at"])

    op.create_table(
        "generation_batches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_type", sa.String(length=16), nullable=False),
        sa.Column("source_sample_batch_id", sa.BigInteger(), nullable=True),
        sa.Column("product_name", sa.String(length=60), nullable=False),
        sa.Column("style_text", sa.String(length=50), nullable=True),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("template_name", sa.String(length=50), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("params_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("requirement_summary", postgresql.JSONB(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("client_request_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("batch_type IN ('sample','full')", name="ck_batches_type"),
        sa.CheckConstraint(
            "status IN ('queued','running','sample_ready','confirmed','completed',"
            "'partially_failed','failed','cancelled')",
            name="ck_batches_status",
        ),
        sa.CheckConstraint(
            "stage IS NULL OR stage IN ('planner','product_understanding','copywriter',"
            "'prompt_builder','image_generator','quality_reviewer','repairer','platform_rule',"
            "'text_composition','done')",
            name="ck_batches_stage",
        ),
        sa.CheckConstraint(
            "(batch_type = 'full' AND source_sample_batch_id IS NOT NULL) OR "
            "(batch_type = 'sample' AND source_sample_batch_id IS NULL)",
            name="ck_batches_source",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["creative_sessions.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "uq_batches_client_request", "generation_batches", ["client_request_id"],
        unique=True, postgresql_where=sa.text("client_request_id IS NOT NULL"),
    )
    op.create_index("idx_batches_user_time", "generation_batches", ["user_id", "created_at"])
    op.create_index("idx_batches_session_time", "generation_batches", ["session_id", "created_at"])
    op.create_index("idx_batches_status", "generation_batches", ["status"])
    op.create_index("idx_batches_type", "generation_batches", ["batch_type"])

    op.create_table(
        "generated_images",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("image_type", sa.String(length=16), nullable=False),
        sa.Column("image_role", sa.String(length=16), nullable=False),
        sa.Column("index_no", sa.Integer(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("source_image_id", sa.BigInteger(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("is_history_visible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("image_type IN ('sample','final')", name="ck_images_type"),
        sa.CheckConstraint("image_role IN ('main','detail')", name="ck_images_role"),
        sa.CheckConstraint(
            "status IN ('pending','generating','success','failed','cancelled','superseded')",
            name="ck_images_status",
        ),
        sa.ForeignKeyConstraint(["batch_id"], ["generation_batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["creative_sessions.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_images_batch_index", "generated_images", ["batch_id", "index_no", "attempt_no"])
    op.create_index("idx_images_user_history", "generated_images", ["user_id", "is_history_visible", "created_at"])
    op.create_index("idx_images_status", "generated_images", ["status"])
    op.create_index("idx_images_archived_at", "generated_images", ["archived_at"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("batch_id", sa.BigInteger(), nullable=True),
        sa.Column("image_id", sa.BigInteger(), nullable=True),
        sa.Column("agent_code", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("input_full", sa.Text(), nullable=True),
        sa.Column("output_full", sa.Text(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('success','failed','skipped')", name="ck_agent_runs_status"),
        sa.ForeignKeyConstraint(["session_id"], ["creative_sessions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["message_id"], ["chat_messages.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["generation_batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["image_id"], ["generated_images.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_agent_runs_session", "agent_runs", ["session_id", "created_at"])
    op.create_index("idx_agent_runs_batch", "agent_runs", ["batch_id", "created_at"])
    op.create_index("idx_agent_runs_image", "agent_runs", ["image_id"])
    op.create_index("idx_agent_runs_agent_time", "agent_runs", ["agent_code", "created_at"])
    op.create_index("idx_agent_runs_created_at", "agent_runs", ["created_at"])

    op.create_table(
        "uploaded_assets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'active'")),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active','deleted')", name="ck_uploads_status"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["session_id"], ["creative_sessions.id"], ondelete="RESTRICT"),
    )
    op.create_index("idx_uploads_user_session", "uploaded_assets", ["user_id", "session_id", "sort_order"])
    op.create_index("idx_uploads_status", "uploaded_assets", ["status"])
    op.create_index("idx_uploads_archived_at", "uploaded_assets", ["archived_at"])


def downgrade() -> None:
    op.drop_table("uploaded_assets")
    op.drop_index("idx_agent_runs_created_at", table_name="agent_runs")
    op.drop_index("idx_agent_runs_agent_time", table_name="agent_runs")
    op.drop_index("idx_agent_runs_image", table_name="agent_runs")
    op.drop_index("idx_agent_runs_batch", table_name="agent_runs")
    op.drop_index("idx_agent_runs_session", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("idx_images_archived_at", table_name="generated_images")
    op.drop_index("idx_images_status", table_name="generated_images")
    op.drop_index("idx_images_user_history", table_name="generated_images")
    op.drop_index("idx_images_batch_index", table_name="generated_images")
    op.drop_table("generated_images")
    op.drop_index("idx_batches_type", table_name="generation_batches")
    op.drop_index("idx_batches_status", table_name="generation_batches")
    op.drop_index("idx_batches_session_time", table_name="generation_batches")
    op.drop_index("idx_batches_user_time", table_name="generation_batches")
    op.drop_index("uq_batches_client_request", table_name="generation_batches")
    op.drop_table("generation_batches")
    op.drop_index("idx_messages_created_at", table_name="chat_messages")
    op.drop_index("idx_messages_session_time", table_name="chat_messages")
    op.drop_index("uq_messages_session_client", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("idx_sessions_last_message_at", table_name="creative_sessions")
    op.drop_index("idx_sessions_user_status_time", table_name="creative_sessions")
    op.drop_table("creative_sessions")
