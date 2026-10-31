"""generated_images 单张重试幂等键（4 号生图任务）

Revision ID: 0004_image_client_request
Revises: 0003_config_domain
Create Date: 2026-10-31

4 号 demo 为单张重试/重生成增加内部幂等键 `client_request_id`。
该列不属于 10 号 §4.10 的公开字段，但用于保证同一请求重复提交返回同一新图片。
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_image_client_request"
down_revision = "0003_config_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "generated_images",
        sa.Column("client_request_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_images_client_request",
        "generated_images",
        ["client_request_id"],
        unique=True,
        postgresql_where=sa.text("client_request_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_images_client_request", table_name="generated_images")
    op.drop_column("generated_images", "client_request_id")
